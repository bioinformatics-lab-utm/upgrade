"""
Pipeline notifications.

Rows in `notifications` are created by the database trigger on pipeline_runs
(database/migrations/016_pipeline_notifications.sql) whenever a run changes
status. This module reads them for the dashboard's bell menu and sends the
emails the trigger queued (email_status = 'pending').
"""
import asyncio
import logging
from datetime import datetime, timedelta

from services.email_service import (
    EmailSendError,
    build_frontend_link,
    send_pipeline_finished_email,
)

logger = logging.getLogger(__name__)

EMAIL_DISPATCH_INTERVAL_SECONDS = 20
EMAIL_BATCH_SIZE = 20
EMAIL_MAX_ATTEMPTS = 3
EMAIL_RETRY_BACKOFF = timedelta(minutes=5)

_NOTIFICATION_COLUMNS = """
    notification_id, pipeline_id, type, title, message, sample_code, created_at, read_at
"""


def _serialize(row) -> dict:
    return {
        'notification_id': row['notification_id'],
        'pipeline_id': row['pipeline_id'],
        'type': row['type'],
        'title': row['title'],
        'message': row['message'],
        'sample_code': row['sample_code'],
        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        'read': row['read_at'] is not None,
    }


async def list_notifications(conn, user_id: int, limit: int = 20) -> tuple[list[dict], int]:
    """The user's most recent notifications and how many of all of them are unread."""
    rows = await conn.fetch(
        f"""
        SELECT {_NOTIFICATION_COLUMNS}
        FROM notifications
        WHERE user_id = $1
        ORDER BY created_at DESC, notification_id DESC
        LIMIT $2
        """,
        user_id, limit
    )
    unread = await conn.fetchval(
        "SELECT COUNT(*) FROM notifications WHERE user_id = $1 AND read_at IS NULL",
        user_id
    )
    return [_serialize(r) for r in rows], unread


async def mark_read(conn, user_id: int, notification_id: int) -> bool:
    """Mark one of the user's notifications read. False if it is not theirs."""
    found = await conn.fetchval(
        """
        UPDATE notifications
        SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
        WHERE notification_id = $1 AND user_id = $2
        RETURNING notification_id
        """,
        notification_id, user_id
    )
    return found is not None


async def mark_all_read(conn, user_id: int) -> int:
    result = await conn.execute(
        "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE user_id = $1 AND read_at IS NULL",
        user_id
    )
    return int(result.split()[-1])


async def get_email_preference(conn, user_id: int) -> bool:
    return await conn.fetchval("SELECT notify_email FROM users WHERE user_id = $1", user_id)


async def set_email_preference(conn, user_id: int, enabled: bool) -> None:
    await conn.execute(
        "UPDATE users SET notify_email = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
        enabled, user_id
    )


# ---------------------------------------------------------------------------
# Email dispatch
# ---------------------------------------------------------------------------

def _format_duration(started: datetime | None, finished: datetime | None) -> str | None:
    if not started or not finished:
        return None
    minutes = max(0, int((finished - started).total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes} min"


def _format_timestamp(value: datetime | None) -> str | None:
    return value.strftime('%Y-%m-%d %H:%M UTC') if value else None


def _email_details(row) -> list[tuple[str, str]]:
    details = [
        ('Sample', row['sample_label']),
        ('Pipeline run', f"#{row['pipeline_id']}"),
        ('Started', _format_timestamp(row['started_at'])),
        ('Finished', _format_timestamp(row['completed_at'])),
        ('Duration', _format_duration(row['started_at'], row['completed_at'])),
    ]
    # Only once the results were parsed, otherwise "0" would read as "none found"
    if row['type'] == 'pipeline_completed' and row['results_parsed_at']:
        details.append(('AMR genes detected', str(row['amr_genes'])))
        details.append(('Genera identified', str(row['organisms'])))
    return [(label, value) for label, value in details if value]


async def _claim_pending_emails(conn) -> list:
    """Move a batch of pending emails to 'sending' and return what is needed to send them."""
    return await conn.fetch(
        """
        WITH claimed AS (
            UPDATE notifications n
            SET email_status = 'sending',
                email_attempts = n.email_attempts + 1,
                email_last_attempt_at = CURRENT_TIMESTAMP
            WHERE n.notification_id IN (
                SELECT notification_id
                FROM notifications
                WHERE email_status = 'pending'
                  -- Back off after a failed attempt: 5 min, then 10 min
                  AND (email_last_attempt_at IS NULL
                       OR email_last_attempt_at < CURRENT_TIMESTAMP - email_attempts * $2::interval)
                ORDER BY created_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING n.notification_id, n.user_id, n.pipeline_id, n.type,
                      n.sample_code, n.email_attempts
        )
        SELECT c.*,
               u.username, u.email, u.notify_email,
               COALESCE(NULLIF(pr.sample_name, ''), c.sample_code, 'Pipeline #' || c.pipeline_id) AS sample_label,
               pr.started_at, pr.completed_at, pr.error_message, pr.results_parsed_at,
               (SELECT COUNT(DISTINCT gene_name) FROM resistance_genes rg WHERE rg.pipeline_run_id = c.pipeline_id) AS amr_genes,
               (SELECT COUNT(DISTINCT organism_name) FROM detected_organisms d
                 WHERE d.pipeline_run_id = c.pipeline_id AND d.classification_tool = 'Kraken2') AS organisms
        FROM claimed c
        JOIN users u ON u.user_id = c.user_id
        LEFT JOIN pipeline_runs pr ON pr.pipeline_id = c.pipeline_id
        """,
        EMAIL_BATCH_SIZE, EMAIL_RETRY_BACKOFF
    )


async def _send_notification_email(row) -> None:
    succeeded = row['type'] == 'pipeline_completed'
    if succeeded:
        link = build_frontend_link(f"/results/{row['sample_code'] or row['pipeline_id']}")
    else:
        link = build_frontend_link(f"/pipeline/{row['pipeline_id']}/monitor")
    error = (row['error_message'] or '').strip()
    await send_pipeline_finished_email(
        to=row['email'],
        username=row['username'],
        sample_label=row['sample_label'],
        succeeded=succeeded,
        link=link,
        details=_email_details(row),
        error_message=error[-600:] if error else None,
    )


async def send_pending_emails(pool) -> int:
    """Send every email currently queued by the trigger. Returns how many were sent."""
    sent = 0
    while True:
        async with pool.acquire() as conn:
            batch = await _claim_pending_emails(conn)
        if not batch:
            return sent

        for row in batch:
            status, error = 'sent', None
            if not row['notify_email']:
                # Turned off between the status change and now
                status = None
            else:
                try:
                    await _send_notification_email(row)
                    sent += 1
                except EmailSendError as e:
                    error = str(e)
                    status = 'failed' if row['email_attempts'] >= EMAIL_MAX_ATTEMPTS else 'pending'
                    logger.warning(
                        f"Notification email {row['notification_id']} to user {row['user_id']} "
                        f"failed (attempt {row['email_attempts']}): {e}"
                    )
                except Exception as e:
                    error = f"{type(e).__name__}: {e}"
                    status = 'failed'
                    logger.error(f"Notification email {row['notification_id']} crashed: {e}", exc_info=True)

            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE notifications
                    SET email_status = $2::varchar,
                        email_error = $3::text,
                        email_sent_at = CASE WHEN $2::varchar = 'sent' THEN CURRENT_TIMESTAMP END
                    WHERE notification_id = $1
                    """,
                    row['notification_id'], status, error
                )


async def run_email_dispatcher(pool) -> None:
    """Background loop of the API process: send queued notification emails."""
    # A send interrupted by a restart left its row in 'sending'
    try:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE notifications SET email_status = 'pending' WHERE email_status = 'sending'")
    except Exception as e:
        logger.error(f"Could not requeue interrupted notification emails: {e}")

    while True:
        try:
            sent = await send_pending_emails(pool)
            if sent:
                logger.info(f"Sent {sent} notification email(s)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Notification email dispatch error: {e}")
        await asyncio.sleep(EMAIL_DISPATCH_INTERVAL_SECONDS)

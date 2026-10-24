-- Migration: In-app and email notifications for pipeline status changes
-- Date: 2026-10-16
-- Description: Every status change of a pipeline run (queued -> running ->
-- completed / failed / cancelled) creates a notification for the owner of its
-- sample, shown under the bell icon in the dashboard header. Completed and failed
-- runs are also emailed to the owner, unless they turned email notifications off.
--
-- The notifications are written by a trigger on pipeline_runs, so every code path
-- that changes a run's status (RQ worker, stale-pipeline watchdog, cancel endpoint,
-- batch scripts) is covered without changes to those paths. The backend's
-- notification dispatcher sends the emails (email_status = 'pending').
--
-- The trigger never lets an error escape: a failure to record a notification must
-- not roll back the worker's status update.
-- Idempotent: safe to run more than once.

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_email BOOLEAN NOT NULL DEFAULT true;

COMMENT ON COLUMN users.notify_email IS
    'Email the user when one of their pipeline runs completes or fails';

CREATE TABLE IF NOT EXISTS notifications (
    notification_id BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    pipeline_id     INTEGER REFERENCES pipeline_runs(pipeline_id) ON DELETE CASCADE,
    type            VARCHAR(30) NOT NULL,   -- pipeline_running | pipeline_completed | pipeline_failed | pipeline_cancelled
    title           VARCHAR(255) NOT NULL,
    message         TEXT,
    sample_code     VARCHAR(255),           -- results page address (/results/<sample_code>)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at         TIMESTAMPTZ,
    email_status    VARCHAR(20),            -- NULL (no email) | pending | sending | sent | failed
    email_attempts  SMALLINT NOT NULL DEFAULT 0,
    email_last_attempt_at TIMESTAMPTZ,
    email_sent_at   TIMESTAMPTZ,
    email_error     TEXT
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications (user_id) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notifications_email_pending
    ON notifications (created_at) WHERE email_status = 'pending';

CREATE OR REPLACE FUNCTION notify_pipeline_status_change() RETURNS trigger AS $$
DECLARE
    v_owner       INTEGER;
    v_notify      BOOLEAN;
    v_code        VARCHAR;
    v_label       TEXT;
    v_title       TEXT;
    v_message     TEXT;
    v_email       VARCHAR;
BEGIN
    IF NEW.status NOT IN ('running', 'completed', 'failed', 'cancelled') THEN
        RETURN NEW;
    END IF;

    BEGIN
        SELECT s.owner_id, s.sample_code, u.notify_email
          INTO v_owner, v_code, v_notify
          FROM samples s
          JOIN users u ON u.user_id = s.owner_id
         WHERE s.sample_id = NEW.sample_id;

        IF v_owner IS NULL THEN
            RETURN NEW;
        END IF;

        v_label := COALESCE(NULLIF(NEW.sample_name, ''), v_code, 'Pipeline #' || NEW.pipeline_id);

        CASE NEW.status
            WHEN 'running' THEN
                v_title   := 'Analysis started';
                v_message := v_label || ' left the queue and is now running.';
            WHEN 'completed' THEN
                v_title   := 'Analysis completed';
                v_message := v_label || ' finished successfully. Results are ready.';
            WHEN 'failed' THEN
                v_title   := 'Analysis failed';
                v_message := v_label || ' failed'
                             || COALESCE(': ' || left(NULLIF(NEW.error_message, ''), 200), '.');
            WHEN 'cancelled' THEN
                v_title   := 'Analysis cancelled';
                v_message := v_label || ' was cancelled.';
        END CASE;

        v_email := CASE
            WHEN NEW.status IN ('completed', 'failed') AND v_notify THEN 'pending'
        END;

        INSERT INTO notifications (user_id, pipeline_id, type, title, message, sample_code, email_status)
        VALUES (v_owner, NEW.pipeline_id, 'pipeline_' || NEW.status, v_title, v_message,
                COALESCE(NULLIF(NEW.sample_name, ''), v_code), v_email);
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'notify_pipeline_status_change(pipeline %): %', NEW.pipeline_id, SQLERRM;
    END;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pipeline_status_notification ON pipeline_runs;
CREATE TRIGGER trg_pipeline_status_notification
    AFTER UPDATE OF status ON pipeline_runs
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_pipeline_status_change();

COMMIT;

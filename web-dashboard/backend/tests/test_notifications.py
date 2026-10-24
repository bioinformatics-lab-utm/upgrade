"""
Tests for pipeline notifications (routes/notifications.py, services/notification_service.py)
"""
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

import pytest


def _pool(conn):
    acquire = Mock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=False)
    pool = Mock()
    pool.acquire = Mock(return_value=acquire)
    return pool


def _authed_request(body=None, args=None, conn=None):
    """Mock request carrying a valid JWT for user 7 and a usable db pool"""
    from auth import generate_token

    token = generate_token(user_id=7, username="johndoe", email="john@example.com")

    request = Mock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.ctx = Mock()
    request.json = body
    request.args = args or {}
    request.app.ctx.db_pool = _pool(conn or AsyncMock())
    return request


def _body(response):
    return json.loads(response.body)


class TestNotificationRoutes:
    """Tests for /api/notifications"""

    @pytest.mark.asyncio
    async def test_requires_authentication(self):
        """Test the list rejects requests without a token"""
        from routes.notifications import get_notifications
        from sanic.exceptions import Unauthorized

        request = Mock()
        request.headers = {}
        request.ctx = Mock()

        with pytest.raises(Unauthorized):
            await get_notifications(request)

    @pytest.mark.asyncio
    async def test_lists_own_notifications(self):
        """Test the list is read for the token's user with a clamped limit"""
        from routes.notifications import get_notifications

        request = _authed_request(args={'limit': '500'})
        items = [{'notification_id': 1, 'title': 'Analysis completed', 'read': False}]

        with patch('routes.notifications.list_notifications', new=AsyncMock(return_value=(items, 1))) as listing:
            response = await get_notifications(request)

        assert response.status == 200
        assert _body(response) == {'success': True, 'notifications': items, 'unread_count': 1}
        assert listing.await_args.args[1:] == (7, 50)

    @pytest.mark.asyncio
    async def test_mark_read_of_other_users_notification_is_404(self):
        """Test a notification that is not the user's is reported as missing"""
        from routes.notifications import read_notification

        request = _authed_request()

        with patch('routes.notifications.mark_read', new=AsyncMock(return_value=False)) as mark:
            response = await read_notification(request, 42)

        assert response.status == 404
        assert mark.await_args.args[1:] == (7, 42)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [None, {}, {"email": "no"}, {"email": 0}])
    async def test_preferences_require_boolean(self, body):
        """Test the email preference only accepts true or false"""
        from routes.notifications import update_preferences

        request = _authed_request(body)

        with patch('routes.notifications.set_email_preference', new=AsyncMock()) as save:
            response = await update_preferences(request)

        assert response.status == 400
        save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_preferences_saved(self):
        """Test turning emails off is saved for the token's user"""
        from routes.notifications import update_preferences

        request = _authed_request({"email": False})

        with patch('routes.notifications.set_email_preference', new=AsyncMock()) as save:
            response = await update_preferences(request)

        assert response.status == 200
        assert _body(response)['preferences'] == {'email': False}
        assert save.await_args.args[1:] == (7, False)


def _pending_row(**overrides):
    started = datetime(2026, 10, 16, 8, 0)
    row = {
        'notification_id': 11, 'user_id': 7, 'pipeline_id': 1724, 'type': 'pipeline_completed',
        'sample_code': 'sample_091026_002', 'email_attempts': 1,
        'username': 'johndoe', 'email': 'john@example.com', 'notify_email': True,
        'sample_label': 'sample_091026_002',
        'started_at': started, 'completed_at': started + timedelta(hours=2, minutes=5),
        'error_message': None, 'results_parsed_at': started, 'amr_genes': 18, 'organisms': 3,
    }
    row.update(overrides)
    return row


class TestSendPendingEmails:
    """Tests for send_pending_emails"""

    @staticmethod
    async def _run(rows, send):
        """Run one dispatch over `rows`; returns (conn, number of emails sent)"""
        from services import notification_service

        conn = AsyncMock()
        conn.fetch = AsyncMock(side_effect=[rows, []])
        with patch.object(notification_service, 'send_pipeline_finished_email', new=send):
            return conn, await notification_service.send_pending_emails(_pool(conn))

    @pytest.mark.asyncio
    async def test_completed_run_is_emailed_with_results_link(self):
        """Test a completed run sends a success email pointing at its results page"""
        send = AsyncMock(return_value='<id>')
        conn, sent = await self._run([_pending_row()], send)

        assert sent == 1

        kwargs = send.await_args.kwargs
        assert kwargs['to'] == 'john@example.com'
        assert kwargs['succeeded'] is True
        assert kwargs['link'].endswith('/results/sample_091026_002')
        assert ('Duration', '2h 05m') in kwargs['details']
        assert ('AMR genes detected', '18') in kwargs['details']
        assert conn.execute.await_args.args[1:] == (11, 'sent', None)

    @pytest.mark.asyncio
    async def test_failed_run_links_to_monitor_with_error(self):
        """Test a failed run sends a failure email with the error and no result counts"""
        send = AsyncMock(return_value='<id>')
        row = _pending_row(type='pipeline_failed', error_message='Nextflow exited with 1', results_parsed_at=None)
        conn, sent = await self._run([row], send)


        kwargs = send.await_args.kwargs
        assert kwargs['succeeded'] is False
        assert kwargs['link'].endswith('/pipeline/1724/monitor')
        assert kwargs['error_message'] == 'Nextflow exited with 1'
        assert not any(label == 'AMR genes detected' for label, _ in kwargs['details'])

    @pytest.mark.asyncio
    async def test_smtp_failure_is_retried_then_given_up(self):
        """Test an SMTP error requeues the email until the last attempt"""
        from services.email_service import EmailSendError

        send = AsyncMock(side_effect=EmailSendError('down'))
        conn, sent = await self._run([_pending_row(email_attempts=1), _pending_row(notification_id=12, email_attempts=3)], send)

        assert sent == 0

        statuses = [c.args[1:3] for c in conn.execute.await_args_list]
        assert statuses == [(11, 'pending'), (12, 'failed')]

    @pytest.mark.asyncio
    async def test_preference_turned_off_skips_email(self):
        """Test no email is sent when the user turned emails off after it was queued"""
        send = AsyncMock()
        conn, sent = await self._run([_pending_row(notify_email=False)], send)

        assert sent == 0
        send.assert_not_awaited()
        assert conn.execute.await_args.args[1:] == (11, None, None)

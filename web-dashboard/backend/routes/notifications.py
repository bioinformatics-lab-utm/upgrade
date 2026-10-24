"""
Notification Routes
The signed-in user's pipeline notifications (bell menu) and email preference
"""
from sanic import Blueprint
from sanic.response import json
import logging

from auth import protected
from authz import current_user_id
from services.notification_service import (
    list_notifications,
    mark_read,
    mark_all_read,
    get_email_preference,
    set_email_preference,
)

notifications_bp = Blueprint('notifications', url_prefix='/api/notifications')
logger = logging.getLogger(__name__)

MAX_LIMIT = 50


@notifications_bp.route('', methods=['GET'])
@protected
async def get_notifications(request):
    """
    Most recent notifications of the current user

    Query params:
        limit: how many to return (default 20, max 50)

    Response:
        {
            "success": true,
            "notifications": [
                {"notification_id": 7, "pipeline_id": 1724, "type": "pipeline_completed",
                 "title": "Analysis completed", "message": "...", "sample_code": "sample_091026_002",
                 "created_at": "2026-10-16T09:12:00+00:00", "read": false}
            ],
            "unread_count": 1
        }
    """
    try:
        try:
            limit = min(max(int(request.args.get('limit', 20)), 1), MAX_LIMIT)
        except ValueError:
            limit = 20

        async with request.app.ctx.db_pool.acquire() as conn:
            notifications, unread = await list_notifications(conn, current_user_id(request), limit)

        return json({'success': True, 'notifications': notifications, 'unread_count': unread})

    except Exception as e:
        logger.error(f"Notification list error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@notifications_bp.route('/<notification_id:int>/read', methods=['POST'])
@protected
async def read_notification(request, notification_id):
    """Mark one notification as read"""
    try:
        async with request.app.ctx.db_pool.acquire() as conn:
            found = await mark_read(conn, current_user_id(request), notification_id)

        if not found:
            return json({'success': False, 'error': 'Notification not found'}, status=404)
        return json({'success': True})

    except Exception as e:
        logger.error(f"Notification read error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@notifications_bp.route('/read-all', methods=['POST'])
@protected
async def read_all_notifications(request):
    """Mark all notifications of the current user as read"""
    try:
        async with request.app.ctx.db_pool.acquire() as conn:
            updated = await mark_all_read(conn, current_user_id(request))

        return json({'success': True, 'updated': updated})

    except Exception as e:
        logger.error(f"Notification read-all error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@notifications_bp.route('/preferences', methods=['GET'])
@protected
async def get_preferences(request):
    """
    Response:
        {"success": true, "preferences": {"email": true}}
    """
    try:
        async with request.app.ctx.db_pool.acquire() as conn:
            email = await get_email_preference(conn, current_user_id(request))

        return json({'success': True, 'preferences': {'email': bool(email)}})

    except Exception as e:
        logger.error(f"Notification preferences error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@notifications_bp.route('/preferences', methods=['PUT'])
@protected
async def update_preferences(request):
    """
    Turn the emails sent when an analysis completes or fails on or off

    Request body:
        {"email": false}
    """
    try:
        email = (request.json or {}).get('email')
        if not isinstance(email, bool):
            return json({'success': False, 'error': '"email" must be true or false'}, status=400)

        async with request.app.ctx.db_pool.acquire() as conn:
            await set_email_preference(conn, current_user_id(request), email)

        return json({'success': True, 'preferences': {'email': email}})

    except Exception as e:
        logger.error(f"Notification preferences update error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)

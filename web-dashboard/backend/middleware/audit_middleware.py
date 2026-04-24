"""
Audit Middleware for Sanic
Tracks API endpoint calls with user context for audit logging
"""

import logging
from functools import wraps
from sanic import Request, response
import asyncpg

logger = logging.getLogger(__name__)


class AuditContext:
    """
    Manages audit context for the current request
    Sets PostgreSQL session variables for audit triggers
    """

    @staticmethod
    async def set_context(conn: asyncpg.Connection, user: str = None, ip_address: str = None,
                         request_id: str = None, user_agent: str = None):
        """
        Set audit context in PostgreSQL session
        These values are used by audit triggers

        Args:
            conn: asyncpg connection
            user: Username or API key
            ip_address: Client IP address
            request_id: Request tracking ID
            user_agent: User agent string
        """
        try:
            # Set session variables for audit triggers (parameterized via set_config)
            if user:
                await conn.execute("SELECT set_config('app.current_user', $1, true)", str(user))

            if ip_address:
                await conn.execute("SELECT set_config('app.client_ip', $1, true)", str(ip_address))

            if request_id:
                await conn.execute("SELECT set_config('app.request_id', $1, true)", str(request_id))

            if user_agent:
                await conn.execute("SELECT set_config('app.user_agent', $1, true)", str(user_agent))

            logger.debug(f"Audit context set: user={user}, ip={ip_address}, request_id={request_id}")

        except Exception as e:
            logger.error(f"Failed to set audit context: {e}", exc_info=True)
            # Don't fail the request if audit context can't be set


    @staticmethod
    async def clear_context(conn: asyncpg.Connection):
        """Clear audit context from PostgreSQL session"""
        try:
            await conn.execute("RESET app.current_user")
            await conn.execute("RESET app.client_ip")
            await conn.execute("RESET app.request_id")
            await conn.execute("RESET app.user_agent")
        except Exception as e:
            logger.warning(f"Failed to clear audit context: {e}")


def audit_middleware(app):
    """
    Sanic middleware to set audit context for all requests

    Usage:
        from middleware.audit_middleware import audit_middleware
        audit_middleware(app)
    """

    @app.middleware('request')
    async def setup_audit_context(request: Request):
        """Set audit context before request processing"""
        # Extract user from JWT token or API key
        user = extract_user_from_request(request)

        # Get client IP (handle proxy headers)
        ip_address = request.headers.get('X-Forwarded-For', request.ip)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID', str(request.id))

        # Get user agent
        user_agent = request.headers.get('User-Agent', 'Unknown')

        # Store in request context for later use
        request.ctx.audit_user = user
        request.ctx.audit_ip = ip_address
        request.ctx.audit_request_id = request_id
        request.ctx.audit_user_agent = user_agent

        logger.info(f"Request: {request.method} {request.path} | User: {user} | IP: {ip_address}")


    @app.middleware('response')
    async def log_response(request: Request, response):
        """Log response status for audit"""
        user = getattr(request.ctx, 'audit_user', 'unknown')
        logger.info(f"Response: {response.status} | User: {user} | Path: {request.path}")


def extract_user_from_request(request: Request) -> str:
    """
    Extract user identifier from request

    Priority:
    1. JWT token (Authorization header)
    2. API key (X-API-Key header)
    3. Session user
    4. IP address as fallback

    Args:
        request: Sanic request object

    Returns:
        str: User identifier
    """
    # 1. Try JWT token
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        try:
            import jwt as pyjwt
            import os
            payload = pyjwt.decode(token, os.getenv('JWT_SECRET', ''), algorithms=['HS256'])
            return (payload.get('username')
                    or payload.get('sub')
                    or f"uid_{payload.get('user_id', 'unknown')}")
        except Exception:
            return f"jwt_{token[:8]}"

    # 2. Try API key
    api_key = request.headers.get('X-API-Key')
    if api_key:
        return f"api_{api_key[:8]}"

    # 3. Try session user (if available)
    if hasattr(request.ctx, 'user'):
        return request.ctx.user.get('username', 'session_user')

    # 4. Fallback to IP address
    ip_address = request.headers.get('X-Forwarded-For', request.ip)
    if ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()

    return f"anonymous_{ip_address}"


def audit_endpoint(reason: str = None):
    """
    Decorator to enable audit logging for specific endpoint

    Usage:
        @app.route('/api/pipeline/<pipeline_id>', methods=['DELETE'])
        @audit_endpoint(reason="User requested deletion")
        async def delete_pipeline(request, pipeline_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            # Get audit context from request
            user = getattr(request.ctx, 'audit_user', 'unknown')
            ip_address = getattr(request.ctx, 'audit_ip', request.ip)
            request_id = getattr(request.ctx, 'audit_request_id', str(request.id))
            user_agent = getattr(request.ctx, 'audit_user_agent', 'Unknown')

            logger.info(f"[AUDIT] Endpoint: {request.path} | User: {user} | Reason: {reason}")

            # Execute endpoint
            result = await func(request, *args, **kwargs)

            return result

        return wrapper
    return decorator


async def log_manual_audit(conn: asyncpg.Connection, table_name: str, operation: str,
                           row_id: int, user: str, reason: str = None, metadata: dict = None):
    """
    Manually log audit record (for operations not handled by triggers)

    Args:
        conn: asyncpg connection
        table_name: Name of table being modified
        operation: Operation type (INSERT, UPDATE, DELETE)
        row_id: ID of affected row
        user: Username or identifier
        reason: Human-readable reason for change
        metadata: Additional context as dict

    Example:
        await log_manual_audit(
            conn, 'pipeline_runs', 'DELETE', pipeline_id,
            user='admin@example.com',
            reason='User requested deletion via UI',
            metadata={'ip': '192.168.1.1', 'endpoint': '/api/pipeline/123'}
        )
    """
    import json

    try:
        await conn.execute("""
            INSERT INTO audit_log (
                table_name, operation, row_id,
                changed_by, changed_at, reason, metadata
            ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, $5, $6)
        """, table_name, operation, row_id, user, reason,
             json.dumps(metadata) if metadata else None)

        logger.info(f"[AUDIT] Manual log: {table_name}.{row_id} {operation} by {user}")

    except Exception as e:
        logger.error(f"Failed to log manual audit: {e}")
        # Don't fail the operation if audit logging fails


# ==================== USAGE EXAMPLES ====================

"""
Example 1: Apply middleware to Sanic app
-----------------------------------------

from middleware.audit_middleware import audit_middleware

app = Sanic("genomic-pipeline")
audit_middleware(app)  # Apply to all routes


Example 2: Use audit context in route
--------------------------------------

from middleware.audit_middleware import AuditContext

@app.route('/api/pipeline/<pipeline_id>', methods=['DELETE'])
async def delete_pipeline(request, pipeline_id):
    db_pool = request.app.ctx.db_pool

    async with db_pool.acquire() as conn:
        # Set audit context
        await AuditContext.set_context(
            conn,
            user=request.ctx.audit_user,
            ip_address=request.ctx.audit_ip,
            request_id=request.ctx.audit_request_id
        )

        try:
            # Delete pipeline (audit trigger will log automatically)
            await conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id)

            return response.json({"status": "deleted"})

        finally:
            await AuditContext.clear_context(conn)


Example 3: Manual audit logging for complex operations
-------------------------------------------------------

from middleware.audit_middleware import log_manual_audit

@app.route('/api/bulk-delete', methods=['POST'])
async def bulk_delete(request):
    pipeline_ids = request.json.get('pipeline_ids', [])

    async with db_pool.acquire() as conn:
        for pipeline_id in pipeline_ids:
            await conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id)

            # Manual audit log for bulk operation
            await log_manual_audit(
                conn, 'pipeline_runs', 'DELETE', pipeline_id,
                user=request.ctx.audit_user,
                reason=f"Bulk delete operation (total: {len(pipeline_ids)})",
                metadata={
                    'ip': request.ctx.audit_ip,
                    'endpoint': request.path,
                    'batch_size': len(pipeline_ids)
                }
            )

    return response.json({"deleted": len(pipeline_ids)})


Example 4: Use decorator for critical endpoints
------------------------------------------------

from middleware.audit_middleware import audit_endpoint

@app.route('/api/samples/<sample_id>', methods=['DELETE'])
@audit_endpoint(reason="Sample deletion via API")
async def delete_sample(request, sample_id):
    # Deletion will be automatically audited by trigger
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM samples WHERE sample_id = $1", sample_id)

    return response.json({"status": "deleted"})
"""

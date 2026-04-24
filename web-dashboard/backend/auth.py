"""
Authentication & Authorization Module
JWT-based authentication with user registration and login
"""
import jwt
import bcrypt
import os
import sys
import secrets
from datetime import datetime, timedelta
from functools import wraps
from sanic.response import json
from sanic.exceptions import Unauthorized
import logging

logger = logging.getLogger(__name__)

# JWT bypass: BLOCKED in production, only allowed in development
_env = os.getenv('ENVIRONMENT', 'development').lower()
_bypass_requested = os.getenv('JWT_BYPASS_ENABLED', 'false').lower() == 'true'
if _bypass_requested and _env in ('production', 'prod'):
    logger.critical("SECURITY: JWT_BYPASS_ENABLED is set in production! Ignoring — auth remains enforced.")
    JWT_BYPASS_ENABLED = False
else:
    JWT_BYPASS_ENABLED = _bypass_requested
if JWT_BYPASS_ENABLED:
    logger.warning("JWT_BYPASS_ENABLED=true — authentication is DISABLED (development only).")


def _load_jwt_secret():
    """
    Load JWT secret from Docker secrets file or environment variable.
    SECURITY: Fails fast in production if not configured.
    """
    # Try Docker secrets first
    secret_file = '/run/secrets/jwt_secret'
    if os.path.exists(secret_file):
        with open(secret_file, 'r') as f:
            secret = f.read().strip()
            if secret:
                logger.info("JWT_SECRET loaded from Docker secrets")
                return secret
    
    # Fall back to environment variable
    secret = os.getenv('JWT_SECRET')
    if secret:
        logger.info("JWT_SECRET loaded from environment variable")
        return secret
    
    # In production, we must have a secret
    env = os.getenv('ENVIRONMENT', 'development').lower()
    if env in ('production', 'prod'):
        logger.critical("SECURITY ERROR: JWT_SECRET not configured in production!")
        sys.exit(1)
    
    # Development only: generate a random secret with warning
    logger.warning(
        "JWT_SECRET not set - using auto-generated secret. "
        "This is only acceptable in development. Set JWT_SECRET for production!"
    )
    return secrets.token_hex(32)


# JWT Configuration
JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24  # Token expires in 24 hours

# Password hashing
def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hashed version"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_token(user_id: int, username: str, email: str) -> str:
    """Generate JWT token for user"""
    payload = {
        'user_id': user_id,
        'username': username,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify JWT token"""
    if JWT_BYPASS_ENABLED:
        logger.warning("JWT BYPASS ACTIVE - Token verification skipped!")
        return {
            'user_id': 1,
            'username': 'dev_user',
            'email': 'dev@localhost',
            'exp': (datetime.utcnow() + timedelta(hours=24)).timestamp(),
            'iat': datetime.utcnow().timestamp()
        }

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token has expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")


def extract_token(request):
    """Extract token from Authorization header"""
    if JWT_BYPASS_ENABLED:
        auth_header = request.headers.get('Authorization', '')
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2:
                return parts[1]
        return "bypass_token"

    auth_header = request.headers.get('Authorization', '')

    if not auth_header:
        raise Unauthorized("No authorization header provided")

    parts = auth_header.split()

    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise Unauthorized("Invalid authorization header format. Use: Bearer <token>")

    return parts[1]


def protected(wrapped):
    """
    Decorator to protect routes with JWT authentication.

    Usage:
        @app.route('/api/protected')
        @protected
        async def protected_route(request):
            user = request.ctx.user  # Access user info
            return json({'message': 'Success', 'user': user})
    """
    @wraps(wrapped)
    async def decorator(request, *args, **kwargs):
        if JWT_BYPASS_ENABLED:
            request.ctx.user = {
                'user_id': 1,
                'username': 'dev_user',
                'email': 'dev@localhost'
            }
            return await wrapped(request, *args, **kwargs)

        try:
            token = extract_token(request)
            payload = decode_token(token)

            request.ctx.user = {
                'user_id': payload['user_id'],
                'username': payload['username'],
                'email': payload['email']
            }

            logger.info(f"Authenticated user: {payload['username']} (ID: {payload['user_id']})")

        except Exception as e:
            logger.warning(f"Authentication failed: {e}")
            raise Unauthorized(str(e))

        return await wrapped(request, *args, **kwargs)

    return decorator


async def create_user(conn, username: str, email: str, password: str, full_name: str = None, user_type: str = 'researcher'):
    """
    Create new user in database
    
    Args:
        user_type: One of: lab_technician, public_health_official, researcher, admin
    
    Returns:
        user_id if successful, None if user already exists
    """
    # Check if username or email already exists
    existing = await conn.fetchrow(
        "SELECT user_id FROM users WHERE username = $1 OR email = $2",
        username, email
    )
    
    if existing:
        return None
    
    # Hash password
    password_hash = hash_password(password)
    
    # Split full_name into first_name and last_name
    name_parts = (full_name or '').split(maxsplit=1)
    first_name = name_parts[0] if name_parts else None
    last_name = name_parts[1] if len(name_parts) > 1 else None
    
    # Insert user
    query = """
        INSERT INTO users (username, email, password_hash, first_name, last_name, user_type, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING user_id
    """
    
    user_id = await conn.fetchval(
        query,
        username,
        email,
        password_hash,
        first_name,
        last_name,
        user_type,
        datetime.utcnow()
    )
    
    logger.info(f"Created new user: {username} (ID: {user_id})")
    return user_id


async def authenticate_user(conn, username: str, password: str):
    """
    Authenticate user with username/password
    
    Returns:
        User dict if successful, None if authentication fails
    """
    query = """
        SELECT user_id, username, email, password_hash, first_name, last_name, is_active
        FROM users
        WHERE username = $1 AND is_active = true
    """
    
    user = await conn.fetchrow(query, username)
    
    if not user:
        logger.warning(f"Login failed: user not found - {username}")
        return None
    
    # Verify password
    if not verify_password(password, user['password_hash']):
        logger.warning(f"Login failed: incorrect password - {username}")
        return None
    
    logger.info(f"User authenticated: {username} (ID: {user['user_id']})")
    
    # Combine first_name and last_name into full_name
    full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or None
    
    return {
        'user_id': user['user_id'],
        'username': user['username'],
        'email': user['email'],
        'full_name': full_name
    }


async def get_user_by_id(conn, user_id: int):
    """Get user information by ID"""
    query = """
        SELECT user_id, username, email, first_name, last_name, created_at, last_login
        FROM users
        WHERE user_id = $1 AND is_active = true
    """

    user = await conn.fetchrow(query, user_id)

    if not user:
        return None

    full_name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip() or None

    return {
        'user_id': user['user_id'],
        'username': user['username'],
        'email': user['email'],
        'full_name': full_name,
        'created_at': user['created_at'].isoformat() if user['created_at'] else None,
        'last_login': user['last_login'].isoformat() if user['last_login'] else None
    }


async def update_last_login(conn, user_id: int):
    """Update user's last login timestamp"""
    await conn.execute(
        "UPDATE users SET last_login = $1 WHERE user_id = $2",
        datetime.utcnow(),
        user_id
    )



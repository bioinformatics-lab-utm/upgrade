"""
Authentication & Authorization Module
JWT-based authentication with user registration and login
"""
import jwt
import bcrypt
import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from sanic.response import json
from sanic.exceptions import Unauthorized
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this-in-production')
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
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Token has expired")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid token")


def extract_token(request):
    """Extract token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    
    if not auth_header:
        raise Unauthorized("No authorization header provided")
    
    parts = auth_header.split()
    
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise Unauthorized("Invalid authorization header format. Use: Bearer <token>")
    
    return parts[1]


def protected(wrapped):
    """
    Decorator to protect routes with JWT authentication
    
    Usage:
        @app.route('/api/protected')
        @protected
        async def protected_route(request):
            user = request.ctx.user  # Access user info
            return json({'message': 'Success', 'user': user})
    """
    @wraps(wrapped)
    async def decorator(request, *args, **kwargs):
        try:
            token = extract_token(request)
            payload = decode_token(token)
            
            # Attach user info to request context
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
    
    # Insert user
    query = """
        INSERT INTO users (username, email, password_hash, full_name, user_type, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING user_id
    """
    
    user_id = await conn.fetchval(
        query,
        username,
        email,
        password_hash,
        full_name,
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
        SELECT user_id, username, email, password_hash, full_name, is_active
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
    
    return {
        'user_id': user['user_id'],
        'username': user['username'],
        'email': user['email'],
        'full_name': user['full_name']
    }


async def get_user_by_id(conn, user_id: int):
    """Get user information by ID"""
    query = """
        SELECT user_id, username, email, full_name, created_at, last_login
        FROM users
        WHERE user_id = $1 AND is_active = true
    """
    
    user = await conn.fetchrow(query, user_id)
    
    if not user:
        return None
    
    return {
        'user_id': user['user_id'],
        'username': user['username'],
        'email': user['email'],
        'full_name': user['full_name'],
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


async def generate_verification_token(conn, user_id: int) -> str:
    """
    Generate email verification token for user
    
    Returns:
        64-character verification token
    """
    # Generate random 64-char token
    token = secrets.token_urlsafe(48)  # 48 bytes = 64 chars base64
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    # Store in database
    await conn.execute("""
        INSERT INTO email_verification_tokens (user_id, token, expires_at)
        VALUES ($1, $2, $3)
    """, user_id, token, expires_at)
    
    logger.info(f"Generated verification token for user_id: {user_id}")
    return token


async def verify_email_token(conn, token: str) -> dict:
    """
    Verify email token and mark user as verified
    
    Returns:
        dict with success status and message/user_id
    """
    # Get token from database
    row = await conn.fetchrow("""
        SELECT user_id, expires_at, used_at
        FROM email_verification_tokens
        WHERE token = $1
    """, token)
    
    if not row:
        return {'success': False, 'error': 'Invalid verification token'}
    
    if row['used_at']:
        return {'success': False, 'error': 'Token already used'}
    
    if row['expires_at'] < datetime.utcnow():
        return {'success': False, 'error': 'Token expired. Please request a new one.'}
    
    # Mark token as used
    await conn.execute("""
        UPDATE email_verification_tokens
        SET used_at = $1
        WHERE token = $2
    """, datetime.utcnow(), token)
    
    # Mark user as verified
    await conn.execute("""
        UPDATE users
        SET email_verified = true, email_verified_at = $1
        WHERE user_id = $2
    """, datetime.utcnow(), row['user_id'])
    
    logger.info(f"Email verified for user_id: {row['user_id']}")
    
    return {'success': True, 'user_id': row['user_id']}


async def is_email_verified(conn, user_id: int) -> bool:
    """Check if user's email is verified"""
    verified = await conn.fetchval(
        "SELECT email_verified FROM users WHERE user_id = $1",
        user_id
    )
    return verified or False

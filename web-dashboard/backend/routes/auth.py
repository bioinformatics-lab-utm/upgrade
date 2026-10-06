"""
Authentication Routes
User registration, login, and profile management
"""
from sanic import Blueprint
from sanic.response import json
from sanic.exceptions import BadRequest, Unauthorized, NotFound
import re
import logging

from auth import (
    create_user,
    authenticate_user,
    generate_token,
    protected,
    get_user_by_id,
    update_last_login,
    create_email_verification_token,
    verify_email_token,
    get_unverified_user,
)
from services.email_service import send_verification_email, EmailSendError

# Rate limiting to prevent brute-force attacks
from rate_limiter import rate_limit

auth_bp = Blueprint('auth', url_prefix='/api/auth')
logger = logging.getLogger(__name__)

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(EMAIL_REGEX.match(email))


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    
    Requirements:
    - At least 8 characters
    - Contains uppercase and lowercase
    - Contains at least one digit
    - Contains at least one special character
    
    Returns:
        (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, ""


@auth_bp.route('/register', methods=['POST'])
@rate_limit("5/minute", error_message="Too many registration attempts. Please try again in a minute.")
async def register(request):
    """
    Register new user
    
    Request body:
        {
            "username": "johndoe",
            "email": "john@example.com",
            "password": "SecurePass123!",
            "full_name": "John Doe" (optional)
        }
    
    The account cannot sign in until the email is confirmed via the link
    sent by email. No JWT is issued here.

    Response:
        {
            "success": true,
            "message": "Account created. Check your email to confirm it.",
            "user": {
                "user_id": 1,
                "username": "johndoe",
                "email": "john@example.com"
            },
            "email_sent": true
        }
    """
    try:
        data = request.json
        
        # Validate required fields
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        full_name = data.get('full_name', '').strip()
        
        if not username or not email or not password:
            raise BadRequest("Username, email, and password are required")
        
        # Validate username (alphanumeric and underscore, 3-30 chars)
        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
            raise BadRequest("Username must be 3-30 characters (letters, numbers, underscore only)")
        
        # Validate email
        if not validate_email(email):
            raise BadRequest("Invalid email format")
        
        # Validate password strength
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            raise BadRequest(error_msg)
        
        # Create user
        async with request.app.ctx.db_pool.acquire() as conn:
            user_id = await create_user(conn, username, email, password, full_name)

            if not user_id:
                raise BadRequest("Username or email already exists")

            verification_token = await create_email_verification_token(conn, user_id)

        logger.info(f"New user registered: {username} (ID: {user_id})")

        # The account exists even if the email fails; the user can request a resend
        email_sent = True
        try:
            await send_verification_email(email, username, verification_token)
        except EmailSendError as e:
            email_sent = False
            logger.error(f"Could not send verification email to user {username} (ID: {user_id}): {e}")

        return json({
            'success': True,
            'message': (
                'Account created. Check your email to confirm it.' if email_sent
                else 'Account created, but the confirmation email could not be sent. Please request a new one.'
            ),
            'user': {
                'user_id': user_id,
                'username': username,
                'email': email,
                'full_name': full_name,
            },
            'email_sent': email_sent
        }, status=201)
        
    except BadRequest as e:
        logger.warning(f"Registration failed: {str(e)}")
        return json({'success': False, 'error': str(e)}, status=400)
    
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@auth_bp.route('/login', methods=['POST'])
@rate_limit("5/minute", error_message="Too many login attempts. Please try again in a minute.")
async def login(request):
    """
    User login
    
    Request body:
        {
            "username": "johndoe",
            "password": "SecurePass123!"
        }
    
    Response:
        {
            "success": true,
            "message": "Login successful",
            "user": {
                "user_id": 1,
                "username": "johndoe",
                "email": "john@example.com",
                "full_name": "John Doe"
            },
            "token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }
    """
    try:
        data = request.json
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            raise BadRequest("Username and password are required")
        
        # Authenticate user
        async with request.app.ctx.db_pool.acquire() as conn:
            user = await authenticate_user(conn, username, password)
            
            if not user:
                raise Unauthorized("Invalid username or password")

            if not user['email_verified']:
                logger.warning(f"Login blocked: email not verified - {username}")
                return json({
                    'success': False,
                    'error': 'Please confirm your email address before signing in. Check your inbox for the confirmation link.',
                    'code': 'email_not_verified'
                }, status=403)

            # Update last login
            await update_last_login(conn, user['user_id'])
        
        # Generate JWT token
        token = generate_token(user['user_id'], user['username'], user['email'])
        
        logger.info(f"User logged in: {username}")
        
        return json({
            'success': True,
            'message': 'Login successful',
            'user': user,
            'token': token
        })
        
    except (BadRequest, Unauthorized) as e:
        logger.warning(f"Login failed: {str(e)}")
        return json({'success': False, 'error': str(e)}, status=401)
    
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@auth_bp.route('/me', methods=['GET'])
@protected
async def get_profile(request):
    """
    Get current user profile (requires authentication)
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
        {
            "success": true,
            "user": {
                "user_id": 1,
                "username": "johndoe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "created_at": "2025-01-01T00:00:00",
                "last_login": "2025-01-10T10:30:00"
            }
        }
    """
    try:
        user_id = request.ctx.user['user_id']
        
        async with request.app.ctx.db_pool.acquire() as conn:
            user = await get_user_by_id(conn, user_id)
            
            if not user:
                raise NotFound("User not found")
        
        return json({
            'success': True,
            'user': user
        })
        
    except Exception as e:
        logger.error(f"Profile fetch error: {e}", exc_info=True)
        return json({'success': False, 'error': str(e)}, status=500)


@auth_bp.route('/verify', methods=['GET'])
@protected
async def verify_token(request):
    """
    Verify if token is valid (requires authentication)
    
    Headers:
        Authorization: Bearer <token>
    
    Response:
        {
            "success": true,
            "valid": true,
            "user": {
                "user_id": 1,
                "username": "johndoe",
                "email": "john@example.com"
            }
        }
    """
    return json({
        'success': True,
        'valid': True,
        'user': request.ctx.user
    })


@auth_bp.route('/verify-email', methods=['POST'])
@rate_limit("10/minute", error_message="Too many attempts. Please try again in a minute.")
async def verify_email(request):
    """
    Confirm an email address using the token from the confirmation link

    Request body:
        {"token": "<token from the link>"}

    Response:
        {"success": true, "status": "verified" | "already_verified"}
        {"success": false, "status": "expired" | "invalid", "error": "..."}
    """
    try:
        token = ((request.json or {}).get('token') or '').strip()
        if not token:
            return json({'success': False, 'status': 'invalid', 'error': 'Missing confirmation token'}, status=400)

        async with request.app.ctx.db_pool.acquire() as conn:
            status, _ = await verify_email_token(conn, token)

        if status in ('verified', 'already_verified'):
            return json({'success': True, 'status': status})

        errors = {
            'expired': 'This confirmation link has expired. Request a new one from the sign-in page.',
            'invalid': 'This confirmation link is invalid.',
        }
        return json({'success': False, 'status': status, 'error': errors[status]}, status=400)

    except Exception as e:
        logger.error(f"Email verification error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)


@auth_bp.route('/resend-verification', methods=['POST'])
@rate_limit("3/minute", error_message="Too many requests. Please try again in a minute.")
async def resend_verification(request):
    """
    Send a new confirmation email

    Request body:
        {"identifier": "<username or email>"}

    Always answers with the same message so it cannot be used to discover
    which accounts exist.
    """
    generic = {
        'success': True,
        'message': 'If an unconfirmed account matches, a new confirmation email has been sent.'
    }
    try:
        identifier = ((request.json or {}).get('identifier') or '').strip()
        if not identifier:
            return json({'success': False, 'error': 'Username or email is required'}, status=400)

        async with request.app.ctx.db_pool.acquire() as conn:
            user = await get_unverified_user(conn, identifier)
            if not user:
                return json(generic)
            token = await create_email_verification_token(conn, user['user_id'])

        try:
            await send_verification_email(user['email'], user['username'], token)
        except EmailSendError as e:
            logger.error(f"Could not resend verification email to user {user['username']}: {e}")
            return json({'success': False, 'error': 'Could not send the email. Please try again later.'}, status=502)

        return json(generic)

    except Exception as e:
        logger.error(f"Resend verification error: {e}", exc_info=True)
        return json({'success': False, 'error': 'Internal server error'}, status=500)

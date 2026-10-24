"""
Tests for Authentication module
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import jwt
from datetime import datetime, timedelta
from sanic.exceptions import Unauthorized


class TestPasswordHashing:
    """Tests for password hashing functions"""

    def test_hash_password(self):
        """Test password hashing"""
        from auth import hash_password
        
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_hash_password_unique_salts(self):
        """Test password hashing uses unique salts"""
        from auth import hash_password
        
        password = "SamePassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Same password should produce different hashes (different salts)
        assert hash1 != hash2

    def test_verify_password_success(self):
        """Test successful password verification"""
        from auth import hash_password, verify_password
        
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_password_failure(self):
        """Test failed password verification"""
        from auth import hash_password, verify_password
        
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        assert verify_password("WrongPassword", hashed) is False


class TestJWTTokens:
    """Tests for JWT token functions"""

    def test_generate_token(self):
        """Test generating JWT token"""
        from auth import generate_token
        
        token = generate_token(
            user_id=1,
            username="testuser",
            email="test@example.com"
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_token(self):
        """Test decoding JWT token"""
        from auth import generate_token, decode_token
        
        token = generate_token(
            user_id=1,
            username="testuser",
            email="test@example.com"
        )
        
        decoded = decode_token(token)
        
        assert decoded["user_id"] == 1
        assert decoded["username"] == "testuser"
        assert decoded["email"] == "test@example.com"

    def test_decode_token_expired(self):
        """Test decoding expired token raises Unauthorized"""
        from auth import decode_token, JWT_SECRET, JWT_ALGORITHM
        
        # Create an expired token
        expired_payload = {
            'user_id': 1,
            'username': 'testuser',
            'email': 'test@example.com',
            'exp': datetime.utcnow() - timedelta(hours=1),  # Already expired
            'iat': datetime.utcnow() - timedelta(hours=2)
        }
        expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        with pytest.raises(Unauthorized):
            decode_token(expired_token)

    def test_decode_token_invalid(self):
        """Test decoding invalid token raises Unauthorized"""
        from auth import decode_token
        
        with pytest.raises(Unauthorized):
            decode_token("invalid.token.here")

    def test_token_contains_required_claims(self):
        """Test generated token contains required claims"""
        from auth import generate_token, decode_token
        
        token = generate_token(
            user_id=42,
            username="testuser",
            email="test@example.com"
        )
        
        decoded = decode_token(token)
        
        assert "user_id" in decoded
        assert "username" in decoded
        assert "email" in decoded
        assert "exp" in decoded
        assert "iat" in decoded


class TestExtractToken:
    """Tests for extract_token function"""

    def test_extract_token_success(self):
        """Test extracting token from valid header"""
        from auth import extract_token
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer validtoken123"}
        
        token = extract_token(mock_request)
        
        assert token == "validtoken123"

    def test_extract_token_no_header(self):
        """Test extract_token with no Authorization header"""
        from auth import extract_token
        
        mock_request = Mock()
        mock_request.headers = {}
        
        with pytest.raises(Unauthorized):
            extract_token(mock_request)

    def test_extract_token_invalid_format(self):
        """Test extract_token with invalid header format"""
        from auth import extract_token
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": "InvalidFormat"}
        
        with pytest.raises(Unauthorized):
            extract_token(mock_request)

    def test_extract_token_not_bearer(self):
        """Test extract_token with non-Bearer scheme"""
        from auth import extract_token
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Basic token123"}
        
        with pytest.raises(Unauthorized):
            extract_token(mock_request)


class TestProtectedDecorator:
    """Tests for protected decorator"""

    @pytest.mark.asyncio
    async def test_protected_allows_valid_token(self):
        """Test protected decorator allows valid token"""
        from auth import protected, generate_token
        
        # Create a valid token
        token = generate_token(
            user_id=1,
            username="testuser",
            email="test@example.com"
        )
        
        # Mock request with valid token
        mock_request = Mock()
        mock_request.headers = {"Authorization": f"Bearer {token}"}
        mock_request.ctx = Mock()
        
        # Create decorated function
        @protected
        async def test_route(request):
            return {"success": True}
        
        result = await test_route(mock_request)
        
        assert result["success"] is True
        assert mock_request.ctx.user["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_protected_rejects_invalid_token(self):
        """Test protected decorator rejects invalid token"""
        from auth import protected
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer invalidtoken"}
        mock_request.ctx = Mock()
        
        @protected
        async def test_route(request):
            return {"success": True}
        
        with pytest.raises(Unauthorized):
            await test_route(mock_request)

    @pytest.mark.asyncio
    async def test_protected_rejects_no_token(self):
        """Test protected decorator rejects missing token"""
        from auth import protected
        
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.ctx = Mock()
        
        @protected
        async def test_route(request):
            return {"success": True}
        
        with pytest.raises(Unauthorized):
            await test_route(mock_request)


class TestJWTConstants:
    """Tests for JWT constants"""

    def test_jwt_secret_exists(self):
        """Test JWT_SECRET is defined"""
        from auth import JWT_SECRET
        assert JWT_SECRET is not None
        assert len(JWT_SECRET) > 0

    def test_jwt_algorithm_is_hs256(self):
        """Test JWT_ALGORITHM is HS256"""
        from auth import JWT_ALGORITHM
        assert JWT_ALGORITHM == 'HS256'

    def test_jwt_expiration_hours_is_positive(self):
        """Test JWT_EXPIRATION_HOURS is positive"""
        from auth import JWT_EXPIRATION_HOURS
        assert JWT_EXPIRATION_HOURS > 0


def _conn_with_transaction():
    """Mock asyncpg connection whose transaction() works as an async context manager"""
    conn = AsyncMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction)
    return conn


class TestChangeUserPassword:
    """Tests for change_user_password"""

    @pytest.mark.asyncio
    async def test_changes_password_when_current_is_correct(self):
        """Test the new hash is stored when the current password matches"""
        from auth import change_user_password, hash_password, verify_password

        conn = _conn_with_transaction()
        conn.fetchval = AsyncMock(return_value=hash_password("OldPass123!"))

        status = await change_user_password(conn, 7, "OldPass123!", "NewPass456!")

        assert status == 'changed'
        conn.execute.assert_awaited_once()
        query, new_hash, user_id = conn.execute.await_args.args
        assert 'password_changed_at' in query
        assert user_id == 7
        assert verify_password("NewPass456!", new_hash)
        assert not verify_password("OldPass123!", new_hash)

    @pytest.mark.asyncio
    async def test_rejects_wrong_current_password(self):
        """Test nothing is written when the current password is wrong"""
        from auth import change_user_password, hash_password

        conn = _conn_with_transaction()
        conn.fetchval = AsyncMock(return_value=hash_password("OldPass123!"))

        status = await change_user_password(conn, 7, "WrongPass123!", "NewPass456!")

        assert status == 'invalid_current'
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_user(self):
        """Test a missing or inactive user is reported as not found"""
        from auth import change_user_password

        conn = _conn_with_transaction()
        conn.fetchval = AsyncMock(return_value=None)

        status = await change_user_password(conn, 999, "OldPass123!", "NewPass456!")

        assert status == 'not_found'
        conn.execute.assert_not_awaited()


class TestUpdateUserProfile:
    """Tests for update_user_profile"""

    @pytest.mark.asyncio
    async def test_splits_full_name(self):
        """Test full name is stored as first and last name"""
        from auth import update_user_profile

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=7)
        conn.fetchrow = AsyncMock(return_value={
            'user_id': 7, 'username': 'johndoe', 'email': 'john@example.com',
            'first_name': 'John', 'last_name': 'van Doe', 'user_type': 'researcher',
            'email_verified': True, 'created_at': None, 'last_login': None,
            'password_changed_at': None,
        })

        user = await update_user_profile(conn, 7, "John van Doe")

        _, first_name, last_name, user_id = conn.fetchval.await_args.args
        assert (first_name, last_name, user_id) == ('John', 'van Doe', 7)
        assert user['full_name'] == 'John van Doe'
        assert user['user_type'] == 'researcher'

    @pytest.mark.asyncio
    async def test_empty_name_clears_both_parts(self):
        """Test an empty full name clears first and last name"""
        from auth import update_user_profile

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)

        await update_user_profile(conn, 7, "")

        _, first_name, last_name, _ = conn.fetchval.await_args.args
        assert first_name is None
        assert last_name is None

    @pytest.mark.asyncio
    async def test_unknown_user(self):
        """Test a missing or inactive user returns None"""
        from auth import update_user_profile

        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)

        assert await update_user_profile(conn, 999, "John Doe") is None
        conn.fetchrow.assert_not_awaited()


class TestAuthenticateUser:
    """Tests for authenticate_user"""

    @staticmethod
    def _conn_with_user(password):
        from auth import hash_password

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            'user_id': 7, 'username': 'johndoe', 'email': 'john@example.com',
            'password_hash': hash_password(password), 'first_name': 'John', 'last_name': 'Doe',
            'is_active': True, 'email_verified': True,
        })
        return conn

    @pytest.mark.asyncio
    async def test_looks_up_username_or_email(self):
        """Test the login name is matched against the username and the (lowercase) email"""
        from auth import authenticate_user

        conn = self._conn_with_user("Secret123!")

        user = await authenticate_user(conn, "John@Example.com", "Secret123!")

        query, identifier = conn.fetchrow.await_args.args
        assert "username = $1 OR email = lower($1)" in query
        assert identifier == "John@Example.com"
        assert user['username'] == 'johndoe'

    @pytest.mark.asyncio
    async def test_wrong_password(self):
        """Test a wrong password returns None"""
        from auth import authenticate_user

        conn = self._conn_with_user("Secret123!")

        assert await authenticate_user(conn, "john@example.com", "Wrong123!") is None

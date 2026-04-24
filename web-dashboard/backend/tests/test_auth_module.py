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

"""
Tests for Auth Routes blueprint
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestAuthBlueprintSetup:
    """Tests for auth blueprint configuration"""

    def test_auth_bp_import(self):
        """Test auth blueprint can be imported"""
        from routes.auth import auth_bp
        assert auth_bp is not None

    def test_blueprint_name(self):
        """Test blueprint name"""
        from routes.auth import auth_bp
        assert auth_bp.name == 'auth'

    def test_blueprint_url_prefix(self):
        """Test blueprint URL prefix"""
        from routes.auth import auth_bp
        assert auth_bp.url_prefix == '/api/auth'


class TestAuthRouteImports:
    """Tests for auth route imports"""

    def test_sanic_blueprint_type(self):
        """Test auth_bp is Sanic Blueprint"""
        from routes.auth import auth_bp
        from sanic import Blueprint
        assert isinstance(auth_bp, Blueprint)

    def test_module_has_required_functions(self):
        """Test module has required route functions"""
        from routes import auth
        
        # Check key functions exist
        assert hasattr(auth, 'register')
        assert hasattr(auth, 'login')


class TestAuthRouteFunctions:
    """Tests for auth route functions"""

    def test_has_register_function(self):
        """Test module has register function"""
        from routes.auth import register
        assert register is not None

    def test_has_login_function(self):
        """Test module has login function"""
        from routes.auth import login
        assert login is not None

    def test_has_get_profile_function(self):
        """Test module has get_profile function"""
        from routes.auth import get_profile
        assert get_profile is not None

    def test_has_verify_token_function(self):
        """Test module has verify_token function"""
        from routes.auth import verify_token
        assert verify_token is not None

    def test_has_validate_email_function(self):
        """Test module has validate_email function"""
        from routes.auth import validate_email
        assert validate_email is not None

    def test_has_validate_password_function(self):
        """Test module has validate_password function"""
        from routes.auth import validate_password
        assert validate_password is not None


class TestAuthRouteLogger:
    """Tests for auth route logger"""

    def test_module_has_logger(self):
        """Test module has logger"""
        from routes.auth import logger
        import logging
        assert isinstance(logger, logging.Logger)


def _authed_request(body):
    """Mock request carrying a valid JWT for user 7 and a usable db pool"""
    from auth import generate_token

    token = generate_token(user_id=7, username="johndoe", email="john@example.com")

    request = Mock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.ctx = Mock()
    request.json = body

    acquire = Mock()
    acquire.__aenter__ = AsyncMock(return_value=AsyncMock())
    acquire.__aexit__ = AsyncMock(return_value=False)
    request.app.ctx.db_pool.acquire = Mock(return_value=acquire)
    return request


def _body(response):
    import json
    return json.loads(response.body)


class TestChangePasswordRoute:
    """Tests for POST /api/auth/change-password"""

    @pytest.mark.asyncio
    async def test_requires_authentication(self):
        """Test the route rejects requests without a token"""
        from routes.auth import change_password
        from sanic.exceptions import Unauthorized

        request = Mock()
        request.headers = {}
        request.ctx = Mock()

        with pytest.raises(Unauthorized):
            await change_password(request)

    @pytest.mark.asyncio
    async def test_changes_password(self):
        """Test a valid request changes the password of the token's user"""
        from routes.auth import change_password

        request = _authed_request({"current_password": "OldPass123!", "new_password": "NewPass456!"})

        with patch('routes.auth.change_user_password', new=AsyncMock(return_value='changed')) as change:
            response = await change_password(request)

        assert response.status == 200
        assert _body(response)['success'] is True
        assert change.await_args.args[1:] == (7, "OldPass123!", "NewPass456!")

    @pytest.mark.asyncio
    async def test_wrong_current_password_is_400_not_401(self):
        """Test a wrong current password does not look like an expired session"""
        from routes.auth import change_password

        request = _authed_request({"current_password": "WrongPass123!", "new_password": "NewPass456!"})

        with patch('routes.auth.change_user_password', new=AsyncMock(return_value='invalid_current')):
            response = await change_password(request)

        assert response.status == 400
        assert _body(response)['code'] == 'invalid_current_password'

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [
        {},
        {"current_password": "OldPass123!"},
        {"current_password": "OldPass123!", "new_password": "weak"},
        {"current_password": "OldPass123!", "new_password": "OldPass123!"},
        {"current_password": "OldPass123!", "new_password": 12345678},
    ])
    async def test_rejects_invalid_input(self, body):
        """Test missing, weak, unchanged or non-string passwords never reach the database"""
        from routes.auth import change_password

        request = _authed_request(body)

        with patch('routes.auth.change_user_password', new=AsyncMock()) as change:
            response = await change_password(request)

        assert response.status == 400
        assert _body(response)['success'] is False
        change.assert_not_awaited()


class TestUpdateProfileRoute:
    """Tests for PUT /api/auth/me"""

    @pytest.mark.asyncio
    async def test_updates_full_name(self):
        """Test the full name is normalized and saved for the token's user"""
        from routes.auth import update_profile

        request = _authed_request({"full_name": "  John   Doe "})
        updated = {'user_id': 7, 'username': 'johndoe', 'full_name': 'John Doe'}

        with patch('routes.auth.update_user_profile', new=AsyncMock(return_value=updated)) as update:
            response = await update_profile(request)

        assert response.status == 200
        assert _body(response)['user'] == updated
        assert update.await_args.args[1:] == (7, "John Doe")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body", [{}, {"full_name": None}, {"full_name": "x" * 101}])
    async def test_rejects_invalid_input(self, body):
        """Test a missing or too long name is rejected"""
        from routes.auth import update_profile

        request = _authed_request(body)

        with patch('routes.auth.update_user_profile', new=AsyncMock()) as update:
            response = await update_profile(request)

        assert response.status == 400
        update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_user(self):
        """Test a deleted or deactivated user gets 404"""
        from routes.auth import update_profile

        request = _authed_request({"full_name": "John Doe"})

        with patch('routes.auth.update_user_profile', new=AsyncMock(return_value=None)):
            response = await update_profile(request)

        assert response.status == 404

"""
Tests for Audit Middleware
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestAuditContext:
    """Tests for AuditContext class"""

    @pytest.mark.asyncio
    async def test_set_context(self):
        """Test setting audit context in PostgreSQL session"""
        from middleware.audit_middleware import AuditContext
        
        mock_conn = AsyncMock()
        
        await AuditContext.set_context(
            mock_conn,
            user="testuser",
            ip_address="192.168.1.1",
            request_id="req-123",
            user_agent="Mozilla/5.0"
        )
        
        # Should have called execute for each parameter
        assert mock_conn.execute.call_count >= 4

    @pytest.mark.asyncio
    async def test_set_context_escapes_user_agent(self):
        """Test that user_agent single quotes are escaped"""
        from middleware.audit_middleware import AuditContext
        
        mock_conn = AsyncMock()
        
        await AuditContext.set_context(
            mock_conn,
            user_agent="test'quote"
        )
        
        # Should escape single quotes
        calls = [str(call) for call in mock_conn.execute.call_args_list]
        assert any("test''quote" in call for call in calls)

    @pytest.mark.asyncio
    async def test_set_context_handles_error(self):
        """Test that set_context handles errors gracefully"""
        from middleware.audit_middleware import AuditContext
        
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("DB error")
        
        # Should not raise
        await AuditContext.set_context(mock_conn, user="test")

    @pytest.mark.asyncio
    async def test_clear_context(self):
        """Test clearing audit context"""
        from middleware.audit_middleware import AuditContext
        
        mock_conn = AsyncMock()
        
        await AuditContext.clear_context(mock_conn)
        
        assert mock_conn.execute.call_count >= 4

    @pytest.mark.asyncio
    async def test_clear_context_handles_error(self):
        """Test that clear_context handles errors gracefully"""
        from middleware.audit_middleware import AuditContext
        
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("DB error")
        
        # Should not raise
        await AuditContext.clear_context(mock_conn)


class TestExtractUserFromRequest:
    """Tests for extract_user_from_request function"""

    def test_extract_jwt_user(self):
        """Test extracting user from JWT token"""
        from middleware.audit_middleware import extract_user_from_request
        
        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer abc12345token"}
        mock_request.ctx = Mock(spec=[])
        mock_request.ip = "127.0.0.1"
        
        result = extract_user_from_request(mock_request)
        
        assert result.startswith("jwt_")
        assert "abc12345" in result

    def test_extract_api_key_user(self):
        """Test extracting user from API key"""
        from middleware.audit_middleware import extract_user_from_request
        
        mock_request = Mock()
        mock_request.headers = {"X-API-Key": "myapikey123"}
        mock_request.ctx = Mock(spec=[])
        mock_request.ip = "127.0.0.1"
        
        result = extract_user_from_request(mock_request)
        
        assert result.startswith("api_")
        assert "myapikey" in result

    def test_extract_session_user(self):
        """Test extracting user from session"""
        from middleware.audit_middleware import extract_user_from_request
        
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.ctx = Mock()
        mock_request.ctx.user = {"username": "sessionuser"}
        mock_request.ip = "127.0.0.1"
        
        result = extract_user_from_request(mock_request)
        
        assert result == "sessionuser"

    def test_extract_anonymous_user(self):
        """Test fallback to anonymous user with IP"""
        from middleware.audit_middleware import extract_user_from_request
        
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.ctx = Mock(spec=[])
        mock_request.ip = "192.168.1.100"
        
        result = extract_user_from_request(mock_request)
        
        assert result.startswith("anonymous_")
        assert "192.168.1.100" in result

    def test_extract_anonymous_with_forwarded_ip(self):
        """Test extracting IP from X-Forwarded-For header"""
        from middleware.audit_middleware import extract_user_from_request
        
        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        mock_request.ctx = Mock(spec=[])
        mock_request.ip = "127.0.0.1"
        
        result = extract_user_from_request(mock_request)
        
        assert "10.0.0.1" in result


class TestAuditMiddleware:
    """Tests for audit_middleware function"""

    def test_audit_middleware_sets_up_middlewares(self):
        """Test that audit_middleware registers middlewares"""
        from middleware.audit_middleware import audit_middleware
        
        mock_app = Mock()
        mock_app.middleware = Mock(return_value=lambda x: x)
        
        audit_middleware(mock_app)
        
        # Should register both request and response middlewares
        assert mock_app.middleware.call_count == 2


class TestAuditEndpointDecorator:
    """Tests for audit_endpoint decorator"""

    @pytest.mark.asyncio
    async def test_audit_endpoint_calls_handler(self):
        """Test that decorated handler is called"""
        from middleware.audit_middleware import audit_endpoint
        
        @audit_endpoint(reason="Test reason")
        async def my_handler(request):
            return {"success": True}
        
        mock_request = Mock()
        mock_request.ctx = Mock()
        mock_request.ctx.audit_user = "testuser"
        mock_request.ctx.audit_ip = "127.0.0.1"
        mock_request.ctx.audit_request_id = "req-123"
        mock_request.ctx.audit_user_agent = "TestAgent"
        mock_request.path = "/test/path"
        mock_request.id = "123"
        mock_request.ip = "127.0.0.1"
        
        result = await my_handler(mock_request)
        
        assert result["success"] is True


class TestLogManualAudit:
    """Tests for log_manual_audit function"""

    @pytest.mark.asyncio
    async def test_log_manual_audit_success(self):
        """Test logging manual audit record"""
        from middleware.audit_middleware import log_manual_audit
        
        mock_conn = AsyncMock()
        
        await log_manual_audit(
            mock_conn,
            table_name="pipeline_runs",
            operation="DELETE",
            row_id=123,
            user="admin@example.com",
            reason="User requested deletion",
            metadata={"ip": "192.168.1.1"}
        )
        
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_manual_audit_without_metadata(self):
        """Test logging manual audit without metadata"""
        from middleware.audit_middleware import log_manual_audit
        
        mock_conn = AsyncMock()
        
        await log_manual_audit(
            mock_conn,
            table_name="samples",
            operation="UPDATE",
            row_id=456,
            user="user@example.com"
        )
        
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_manual_audit_handles_error(self):
        """Test that log_manual_audit handles errors gracefully"""
        from middleware.audit_middleware import log_manual_audit
        
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("DB error")
        
        # Should not raise
        await log_manual_audit(
            mock_conn,
            table_name="test",
            operation="INSERT",
            row_id=1,
            user="test"
        )

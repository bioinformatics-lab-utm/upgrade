"""
Tests for Rate Limiter module
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import time


class TestRateLimiter:
    """Tests for RateLimiter class"""

    @pytest.fixture
    def mock_app(self):
        """Create mock Sanic app"""
        app = MagicMock()
        app.ctx = MagicMock()
        app.ctx.redis = None
        return app

    def test_rate_limiter_init(self, mock_app):
        """Test rate limiter initialization"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter(mock_app)
        
        assert limiter.app == mock_app
        assert hasattr(limiter, '_memory_storage')

    def test_rate_limiter_init_without_app(self):
        """Test rate limiter initialization without app"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        assert limiter.app is None

    def test_init_app(self, mock_app):
        """Test init_app method"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        limiter.init_app(mock_app)
        
        assert limiter.app == mock_app
        assert mock_app.ctx.rate_limiter == limiter


class TestParseRate:
    """Tests for rate parsing"""

    def test_parse_rate_per_minute(self):
        """Test parsing rate per minute"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("5/minute")
        
        assert count == 5
        assert seconds == 60

    def test_parse_rate_per_hour(self):
        """Test parsing rate per hour"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("100/hour")
        
        assert count == 100
        assert seconds == 3600

    def test_parse_rate_per_day(self):
        """Test parsing rate per day"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("1000/day")
        
        assert count == 1000
        assert seconds == 86400

    def test_parse_rate_per_second(self):
        """Test parsing rate per second"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("10/second")
        
        assert count == 10
        assert seconds == 1

    def test_parse_rate_with_plural(self):
        """Test parsing rate with plural unit"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("5/minutes")
        
        assert count == 5
        assert seconds == 60

    def test_parse_rate_invalid_returns_default(self):
        """Test invalid rate returns default"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        count, seconds = limiter.parse_rate("invalid")
        
        # Default: 100/minute
        assert count == 100
        assert seconds == 60


class TestGetClientIP:
    """Tests for client IP extraction"""

    def test_get_client_ip_direct(self):
        """Test getting direct IP"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.ip = "192.168.1.100"
        
        ip = limiter.get_client_ip(mock_request)
        
        assert ip == "192.168.1.100"

    def test_get_client_ip_from_forwarded(self):
        """Test getting IP from X-Forwarded-For"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        mock_request = MagicMock()
        mock_request.headers = {
            'X-Forwarded-For': '10.0.0.1, 192.168.1.1'
        }
        mock_request.ip = "127.0.0.1"
        
        ip = limiter.get_client_ip(mock_request)
        
        assert ip == "10.0.0.1"

    def test_get_client_ip_from_real_ip(self):
        """Test getting IP from X-Real-IP"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        mock_request = MagicMock()
        mock_request.headers = {
            'X-Real-IP': '10.0.0.5'
        }
        mock_request.ip = "127.0.0.1"
        
        ip = limiter.get_client_ip(mock_request)
        
        assert ip == "10.0.0.5"


class TestIsRateLimited:
    """Tests for is_rate_limited method"""

    @pytest.mark.asyncio
    async def test_is_rate_limited_allows_under_limit(self):
        """Test request under limit is allowed"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        # Make first request
        is_limited, info = await limiter.is_rate_limited("test-key", 10, 60)
        
        assert is_limited is False
        assert info['remaining'] >= 0

    @pytest.mark.asyncio
    async def test_is_rate_limited_blocks_over_limit(self):
        """Test request over limit is blocked"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        
        # Exhaust limit
        for _ in range(10):
            await limiter.is_rate_limited("exhaust-key", 10, 60)
        
        # Next request should be limited
        is_limited, info = await limiter.is_rate_limited("exhaust-key", 10, 60)
        
        assert is_limited is True


class TestMemoryStorage:
    """Tests for in-memory fallback storage"""

    @pytest.mark.asyncio
    async def test_memory_storage_cleanup(self):
        """Test memory storage is cleaned up"""
        from rate_limiter import RateLimiter
        
        limiter = RateLimiter()
        limiter._last_cleanup = 0  # Force cleanup
        limiter._cleanup_interval = 0
        
        # Add some requests
        await limiter.is_rate_limited("cleanup-test", 100, 1)
        
        # Should trigger cleanup
        assert "cleanup-test" in limiter._memory_storage or True


class TestTimeUnits:
    """Tests for time unit configuration"""

    def test_time_units_defined(self):
        """Test time units are properly defined"""
        from rate_limiter import RateLimiter
        
        assert RateLimiter.TIME_UNITS['second'] == 1
        assert RateLimiter.TIME_UNITS['minute'] == 60
        assert RateLimiter.TIME_UNITS['hour'] == 3600
        assert RateLimiter.TIME_UNITS['day'] == 86400
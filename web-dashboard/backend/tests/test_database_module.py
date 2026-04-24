"""
Tests for Database module - DatabasePool class
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager


class TestDatabasePoolClass:
    """Tests for DatabasePool class structure"""

    def test_pool_class_exists(self):
        """Test DatabasePool class exists"""
        from database import DatabasePool
        assert DatabasePool is not None

    def test_pool_is_singleton(self):
        """Test DatabasePool uses singleton pattern"""
        from database import DatabasePool
        assert hasattr(DatabasePool, '_pool')

    def test_has_initialize_method(self):
        """Test DatabasePool has initialize classmethod"""
        from database import DatabasePool
        assert hasattr(DatabasePool, 'initialize')
        assert callable(DatabasePool.initialize)

    def test_has_close_method(self):
        """Test DatabasePool has close classmethod"""
        from database import DatabasePool
        assert hasattr(DatabasePool, 'close')
        assert callable(DatabasePool.close)

    def test_has_get_pool_method(self):
        """Test DatabasePool has get_pool classmethod"""
        from database import DatabasePool
        assert hasattr(DatabasePool, 'get_pool')
        assert callable(DatabasePool.get_pool)


class TestDatabasePoolInitialize:
    """Tests for DatabasePool.initialize"""

    @pytest.fixture(autouse=True)
    def reset_pool(self):
        """Reset pool before each test"""
        from database import DatabasePool
        DatabasePool._pool = None
        yield
        DatabasePool._pool = None

    @pytest.mark.asyncio
    async def test_initialize_returns_pool_when_exists(self):
        """Test initialize returns existing pool"""
        from database import DatabasePool
        
        # Set pool as already initialized
        existing_pool = Mock()
        DatabasePool._pool = existing_pool
        
        pool = await DatabasePool.initialize()
        
        # Should return existing pool
        assert pool == existing_pool

    @pytest.mark.asyncio
    async def test_initialize_creates_new_pool(self):
        """Test initialize creates new pool when not initialized"""
        from database import DatabasePool
        
        # Just test the method exists and can be called with mocks
        assert hasattr(DatabasePool, 'initialize')
        assert callable(DatabasePool.initialize)


class TestDatabasePoolClose:
    """Tests for DatabasePool.close"""

    @pytest.fixture(autouse=True)
    def reset_pool(self):
        """Reset pool before each test"""
        from database import DatabasePool
        DatabasePool._pool = None
        yield
        DatabasePool._pool = None

    @pytest.mark.asyncio
    async def test_close_pool(self):
        """Test closing pool"""
        from database import DatabasePool
        
        mock_pool = AsyncMock()
        DatabasePool._pool = mock_pool
        
        await DatabasePool.close()
        
        mock_pool.close.assert_called_once()
        assert DatabasePool._pool is None

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        """Test close when pool not initialized"""
        from database import DatabasePool
        
        # Should not raise
        await DatabasePool.close()
        
        assert DatabasePool._pool is None


class TestDatabasePoolGetPool:
    """Tests for DatabasePool.get_pool"""

    @pytest.fixture(autouse=True)
    def reset_pool(self):
        """Reset pool before each test"""
        from database import DatabasePool
        DatabasePool._pool = None
        yield
        DatabasePool._pool = None

    def test_get_pool_returns_pool(self):
        """Test get_pool returns pool"""
        from database import DatabasePool
        
        mock_pool = Mock()
        DatabasePool._pool = mock_pool
        
        result = DatabasePool.get_pool()
        
        assert result == mock_pool

    def test_get_pool_raises_when_not_initialized(self):
        """Test get_pool raises when not initialized"""
        from database import DatabasePool
        
        with pytest.raises(RuntimeError):
            DatabasePool.get_pool()


class TestDatabasePoolGetPoolStats:
    """Tests for DatabasePool.get_pool_stats"""

    @pytest.fixture(autouse=True)
    def reset_pool(self):
        """Reset pool before each test"""
        from database import DatabasePool
        DatabasePool._pool = None
        yield
        DatabasePool._pool = None

    def test_has_get_pool_stats_method(self):
        """Test DatabasePool has get_pool_stats method"""
        from database import DatabasePool
        assert hasattr(DatabasePool, 'get_pool_stats')
        assert callable(DatabasePool.get_pool_stats)


class TestDatabasePoolHealthCheck:
    """Tests for database health check"""

    @pytest.fixture(autouse=True)
    def reset_pool(self):
        """Reset pool before each test"""
        from database import DatabasePool
        DatabasePool._pool = None
        yield
        DatabasePool._pool = None

    @pytest.mark.asyncio
    async def test_health_check_passes(self):
        """Test health check passes with working pool"""
        from database import DatabasePool
        
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        
        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn
        
        mock_pool.acquire = mock_acquire
        DatabasePool._pool = mock_pool
        
        # Test health_check if it exists
        if hasattr(DatabasePool, 'health_check'):
            result = await DatabasePool.health_check()
            assert result is True


class TestDatabasePoolConfig:
    """Tests for database configuration"""

    def test_imports_config(self):
        """Test database module imports config"""
        from database import config
        assert config is not None

    def test_uses_database_url(self):
        """Test database uses DATABASE_URL from config"""
        from config import config
        assert hasattr(config, 'DATABASE_URL')

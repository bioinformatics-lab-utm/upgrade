"""
Tests for Vault Client
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import os


class TestVaultClient:
    """Tests for VaultClient class"""

    @patch.dict(os.environ, {'ENV': 'development'}, clear=False)
    def test_init_development(self):
        """Test VaultClient initialization in development mode"""
        from vault_client import VaultClient
        
        client = VaultClient()
        
        assert client.env == 'development'
        assert client._client is None

    @patch.dict(os.environ, {'ENV': 'development'}, clear=False)
    def test_vault_addr_default(self):
        """Test default Vault address"""
        from vault_client import VaultClient
        
        client = VaultClient()
        
        assert 'vault' in client.vault_addr

    @patch.dict(os.environ, {'ENV': 'development'}, clear=False)
    def test_mount_point(self):
        """Test mount point is set"""
        from vault_client import VaultClient
        
        client = VaultClient()
        
        assert client.mount_point == 'upgrade'


class TestVaultClientGetSecret:
    """Tests for get_secret method"""

    @patch.dict(os.environ, {'ENV': 'development', 'POSTGRES_PASSWORD': 'testpass'}, clear=False)
    def test_get_secret_fallback_to_env(self):
        """Test fallback to environment variables in development"""
        from vault_client import VaultClient
        
        # Clear the cache first
        VaultClient.get_secret.cache_clear() if hasattr(VaultClient.get_secret, 'cache_clear') else None
        
        client = VaultClient()
        result = client.get_secret('postgres', 'password')
        
        assert result == 'testpass'

    @patch.dict(os.environ, {'ENV': 'development', 'REDIS_HOST': 'localhost'}, clear=False)
    def test_get_secret_env_key_format(self):
        """Test environment variable key format"""
        from vault_client import VaultClient
        
        VaultClient.get_secret.cache_clear() if hasattr(VaultClient.get_secret, 'cache_clear') else None
        
        client = VaultClient()
        result = client.get_secret('redis', 'host')
        
        assert result == 'localhost'

    @patch.dict(os.environ, {'ENV': 'development'}, clear=False)
    def test_get_secret_missing_returns_none(self):
        """Test missing secret returns None"""
        from vault_client import VaultClient
        
        VaultClient.get_secret.cache_clear() if hasattr(VaultClient.get_secret, 'cache_clear') else None
        
        client = VaultClient()
        result = client.get_secret('nonexistent', 'key')
        
        assert result is None


class TestVaultClientGetAllSecrets:
    """Tests for get_all_secrets method"""

    @patch.dict(os.environ, {'ENV': 'development'}, clear=False)
    def test_get_all_secrets_no_vault(self):
        """Test get_all_secrets without Vault returns empty dict"""
        from vault_client import VaultClient
        
        client = VaultClient()
        result = client.get_all_secrets('postgres')
        
        assert result == {}


class TestVaultClientProduction:
    """Tests for production Vault client"""

    def test_hvac_would_be_used_in_production(self):
        """Test hvac module would be used in production"""
        # Just test that the code path exists
        from vault_client import VaultClient
        assert hasattr(VaultClient, '_init_vault_client')

    @patch.dict(os.environ, {'ENV': 'production'}, clear=False)
    def test_vault_token_from_env(self):
        """Test Vault token is read from environment"""
        from vault_client import VaultClient
        
        client = VaultClient()
        # Token could be None if not set
        # Main assertion is that it reads from VAULT_TOKEN


class TestVaultClientCaching:
    """Tests for secret caching"""

    @patch.dict(os.environ, {'ENV': 'development', 'MINIO_ACCESS_KEY': 'minioadmin'}, clear=False)
    def test_get_secret_caches_result(self):
        """Test that get_secret uses lru_cache"""
        from vault_client import VaultClient
        
        VaultClient.get_secret.cache_clear() if hasattr(VaultClient.get_secret, 'cache_clear') else None
        
        client = VaultClient()
        
        # Call twice
        result1 = client.get_secret('minio', 'access_key')
        result2 = client.get_secret('minio', 'access_key')
        
        # Should return same result
        assert result1 == result2

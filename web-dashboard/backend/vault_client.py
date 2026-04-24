# =============================================================================
# UPGRADE Platform - Vault Python Client
# =============================================================================
# Retrieves secrets from HashiCorp Vault in production
# Falls back to environment variables in development
# =============================================================================

import os
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VaultClient:
    """
    HashiCorp Vault client for secure secret management.
    
    In production, retrieves secrets from Vault.
    In development, falls back to environment variables.
    """
    
    def __init__(self):
        self.env = os.getenv('ENV', 'development')
        self.vault_addr = os.getenv('VAULT_ADDR', 'http://vault:8200')
        self.vault_token = os.getenv('VAULT_TOKEN')
        self.mount_point = 'upgrade'
        self._client = None
        
        if self.env == 'production':
            self._init_vault_client()
    
    def _init_vault_client(self):
        """Initialize Vault client for production."""
        try:
            import hvac
            
            self._client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token
            )
            
            if not self._client.is_authenticated():
                logger.error("Vault authentication failed")
                raise RuntimeError("Vault authentication failed")

            logger.info(f"Connected to Vault at {self.vault_addr}")

        except ImportError:
            logger.warning("hvac not installed. Using environment variables.")
            self._client = None
        except (ConnectionError, OSError, RuntimeError) as e:
            logger.error(f"Failed to connect/authenticate to Vault: {e}")
            self._client = None
        except Exception as e:
            logger.error(f"Unexpected error initializing Vault client: {e}", exc_info=True)
            self._client = None
    
    @lru_cache(maxsize=128)
    def get_secret(self, path: str, key: str) -> Optional[str]:
        """
        Retrieve a secret from Vault.
        
        Args:
            path: Secret path (e.g., 'postgres', 'redis')
            key: Secret key (e.g., 'password', 'host')
        
        Returns:
            Secret value or None if not found
        """
        if self._client:
            try:
                secret = self._client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self.mount_point
                )
                return secret['data']['data'].get(key)
            except (KeyError, TypeError) as e:
                logger.error(f"Unexpected Vault response structure for {path}/{key}: {e}")
                return None
            except Exception as e:
                logger.error(f"Failed to retrieve secret {path}/{key}: {e}")
                return None
        else:
            # Fallback to environment variables
            env_key = f"{path.upper()}_{key.upper()}"
            return os.getenv(env_key)
    
    def get_all_secrets(self, path: str) -> Dict[str, Any]:
        """
        Retrieve all secrets at a path.
        
        Args:
            path: Secret path
        
        Returns:
            Dictionary of all secrets at path
        """
        if self._client:
            try:
                secret = self._client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self.mount_point
                )
                return secret['data']['data']
            except (KeyError, TypeError) as e:
                logger.error(f"Unexpected Vault response structure at {path}: {e}")
                return {}
            except Exception as e:
                logger.error(f"Failed to retrieve secrets at {path}: {e}")
                return {}
        return {}
    
    # =========================================================================
    # Convenience methods for common secrets
    # =========================================================================
    
    def get_postgres_config(self) -> Dict[str, Any]:
        """Get PostgreSQL connection configuration."""
        if self._client:
            return self.get_all_secrets('postgres')
        
        # Fallback for development
        return {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
            'username': os.getenv('POSTGRES_USER', 'upgrade'),
            'password': os.getenv('POSTGRES_PASSWORD', '')
        }
    
    def get_postgres_dsn(self) -> str:
        """Get PostgreSQL connection string."""
        config = self.get_postgres_config()
        return (
            f"postgresql://{config['username']}:{config['password']}"
            f"@{config['host']}:{config['port']}/{config['database']}"
        )
    
    def get_async_postgres_dsn(self) -> str:
        """Get async PostgreSQL connection string (asyncpg)."""
        config = self.get_postgres_config()
        return (
            f"postgresql+asyncpg://{config['username']}:{config['password']}"
            f"@{config['host']}:{config['port']}/{config['database']}"
        )
    
    def get_redis_url(self) -> str:
        """Get Redis connection URL."""
        if self._client:
            password = self.get_secret('redis', 'password')
            host = self.get_secret('redis', 'host') or 'redis'
            port = self.get_secret('redis', 'port') or '6379'
            return f"redis://:{password}@{host}:{port}/0"
        
        # Fallback for development
        password = os.getenv('REDIS_PASSWORD', '')
        host = os.getenv('REDIS_HOST', 'localhost')
        port = os.getenv('REDIS_PORT', '6379')
        if password:
            return f"redis://:{password}@{host}:{port}/0"
        return f"redis://{host}:{port}/0"
    
    def get_minio_credentials(self) -> tuple:
        """Get MinIO access credentials."""
        if self._client:
            access_key = self.get_secret('minio', 'access_key')
            secret_key = self.get_secret('minio', 'secret_key')
            return access_key, secret_key
        
        # Fallback for development
        return (
            os.getenv('MINIO_ROOT_USER', 'minioadmin'),
            os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
        )
    
    def get_minio_config(self) -> Dict[str, Any]:
        """Get full MinIO configuration."""
        access_key, secret_key = self.get_minio_credentials()
        return {
            'endpoint': os.getenv('MINIO_ENDPOINT', 'minio:9000'),
            'access_key': access_key,
            'secret_key': secret_key,
            'secure': os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        }
    
    def get_jwt_secret(self) -> str:
        """Get JWT signing secret."""
        if self._client:
            return self.get_secret('jwt', 'secret')
        return os.getenv('JWT_SECRET', 'development-secret-change-in-production')
    
    def get_jwt_config(self) -> Dict[str, Any]:
        """Get full JWT configuration."""
        if self._client:
            return {
                'secret': self.get_secret('jwt', 'secret'),
                'refresh_secret': self.get_secret('jwt', 'refresh_secret'),
                'algorithm': self.get_secret('jwt', 'algorithm') or 'HS256',
                'expiry': int(self.get_secret('jwt', 'expiry') or 3600),
                'refresh_expiry': int(self.get_secret('jwt', 'refresh_expiry') or 604800)
            }
        
        # Fallback for development
        return {
            'secret': os.getenv('JWT_SECRET', 'development-secret'),
            'refresh_secret': os.getenv('JWT_REFRESH_SECRET', 'development-refresh-secret'),
            'algorithm': 'HS256',
            'expiry': 3600,
            'refresh_expiry': 604800
        }
    
    def get_sentry_dsn(self) -> Optional[str]:
        """Get Sentry DSN for error tracking."""
        if self._client:
            return self.get_secret('sentry', 'dsn')
        return os.getenv('SENTRY_DSN')
    
    def get_internal_api_key(self) -> str:
        """Get internal API key for service-to-service auth."""
        if self._client:
            return self.get_secret('api_keys', 'internal_api_key')
        return os.getenv('INTERNAL_API_KEY', 'development-api-key')
    
    def clear_cache(self):
        """Clear the secret cache (e.g., after rotation)."""
        self.get_secret.cache_clear()
        logger.info("Secret cache cleared")


# Singleton instance
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    """Get or create the Vault client singleton."""
    global _vault_client
    if _vault_client is None:
        _vault_client = VaultClient()
    return _vault_client


# Convenience exports
vault = get_vault_client()

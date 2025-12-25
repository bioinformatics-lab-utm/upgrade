"""
Configuration module for reading secrets and environment variables
"""
import os
from pathlib import Path


class Config:
    """Application configuration with Docker secrets support"""

    @staticmethod
    def get_secret(secret_name: str, default: str = None) -> str:
        """
        Read secret from Docker secret file or fallback to environment variable

        Args:
            secret_name: Name of the secret (e.g., 'postgres_password')
            default: Default value if secret not found

        Returns:
            Secret value as string
        """
        # Try to read from Docker secret
        secret_path = Path(f'/run/secrets/{secret_name}')
        if secret_path.exists():
            return secret_path.read_text().strip()

        # Fallback to environment variable (for development)
        env_var = secret_name.upper()
        return os.getenv(env_var, default)

    # Database configuration
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'upgrade_db')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'upgrade')
    
    # ⚠️  SECURITY: No default password - must be set via Docker secret or env var
    _postgres_pass = get_secret.__func__('postgres_password', None)
    if not _postgres_pass:
        import logging
        logging.warning("⚠️  POSTGRES_PASSWORD not set! Set /run/secrets/postgres_password or POSTGRES_PASSWORD env var")
        _postgres_pass = 'CHANGE_ME_IN_PRODUCTION'
    POSTGRES_PASSWORD = _postgres_pass

    @property
    def DATABASE_URL(self) -> str:
        """PostgreSQL connection URL with URL-encoded password"""
        from urllib.parse import quote_plus
        return f"postgresql://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis configuration
    REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    
    # ⚠️  SECURITY: No default password - must be set via Docker secret or env var
    _redis_pass = get_secret.__func__('redis_password', None)
    if not _redis_pass:
        import logging
        logging.warning("⚠️  REDIS_PASSWORD not set! Set /run/secrets/redis_password or REDIS_PASSWORD env var")
        _redis_pass = 'CHANGE_ME_IN_PRODUCTION'
    REDIS_PASSWORD = _redis_pass

    @property
    def REDIS_URL(self) -> str:
        """Redis connection URL"""
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # MinIO configuration
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')  # Internal Docker network
    MINIO_EXTERNAL_ENDPOINT = os.getenv('MINIO_EXTERNAL_ENDPOINT', 'localhost:9000')  # External access
    MINIO_ROOT_USER = os.getenv('MINIO_ROOT_USER', 'minioadmin')
    
    # ⚠️  SECURITY: No default password - must be set via Docker secret or env var
    _minio_pass = get_secret.__func__('minio_root_password', None)
    if not _minio_pass:
        import logging
        logging.warning("⚠️  MINIO_ROOT_PASSWORD not set! Set /run/secrets/minio_root_password or MINIO_ROOT_PASSWORD env var")
        _minio_pass = 'CHANGE_ME_IN_PRODUCTION'
    MINIO_ROOT_PASSWORD = _minio_pass
    
    MINIO_SECURE = os.getenv('MINIO_SECURE', 'false').lower() == 'true'

    # Sanic configuration
    SANIC_PORT = int(os.getenv('SANIC_PORT', 8000))
    SANIC_DEBUG = os.getenv('SANIC_DEBUG', 'false').lower() == 'true'
    SANIC_AUTO_RELOAD = os.getenv('SANIC_AUTO_RELOAD', 'false').lower() == 'true'

    # Nextflow configuration
    NEXTFLOW_DIR = Path(os.getenv('NEXTFLOW_DIR', '/nextflow'))
    RESULTS_DIR = Path(os.getenv('RESULTS_DIR', '/results'))
    DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))
    WORK_DIR = Path(os.getenv('WORK_DIR', '/tmp/nextflow-work'))

    # Redis Queue configuration
    RQ_QUEUE_NAME = os.getenv('RQ_QUEUE_NAME', 'pipeline-queue')
    RQ_JOB_TIMEOUT = int(os.getenv('RQ_JOB_TIMEOUT', 7200))  # 2 hours default

    # Logging configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # CORS configuration
    # Default: Allow all origins (*) - INSECURE but useful for development
    # Production: Set ALLOWED_ORIGINS to comma-separated list of domains
    # Example: ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*')


# Singleton instance
config = Config()

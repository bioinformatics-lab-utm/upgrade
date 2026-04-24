"""
Configuration module for reading secrets and environment variables
"""
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _require_secret(secret_name: str, env_var: str) -> str:
    """
    Load a secret from Docker secrets file or environment variable.
    Exits with error if not configured (no hardcoded fallbacks).
    """
    secret_path = Path(f'/run/secrets/{secret_name}')
    if secret_path.exists():
        value = secret_path.read_text().strip()
        if value:
            return value

    value = os.getenv(env_var)
    if value:
        return value

    logger.critical(
        f"{env_var} not set! Configure via /run/secrets/{secret_name} or {env_var} env var."
    )
    sys.exit(1)


class Config:
    """Application configuration with Docker secrets support"""

    # Database configuration
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'upgrade_db')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'upgrade')
    POSTGRES_PASSWORD = _require_secret('postgres_password', 'POSTGRES_PASSWORD')

    @property
    def DATABASE_URL(self) -> str:
        """PostgreSQL connection URL with URL-encoded password"""
        from urllib.parse import quote_plus
        return f"postgresql://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis configuration
    REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = _require_secret('redis_password', 'REDIS_PASSWORD')

    @property
    def REDIS_URL(self) -> str:
        """Redis connection URL"""
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # MinIO configuration
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
    MINIO_EXTERNAL_ENDPOINT = os.getenv('MINIO_EXTERNAL_ENDPOINT', 'localhost:9000')
    MINIO_ROOT_USER = _require_secret('minio_root_user', 'MINIO_ROOT_USER')
    MINIO_ROOT_PASSWORD = _require_secret('minio_root_password', 'MINIO_ROOT_PASSWORD')

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
    RQ_JOB_TIMEOUT = int(os.getenv('RQ_JOB_TIMEOUT', 43200))  # 12 hours default (was 2h - too short for assembly)

    # Logging configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # CORS configuration
    # Default: Allow all origins (*) - INSECURE but useful for development
    # Production: Set ALLOWED_ORIGINS to comma-separated list of domains
    # Example: ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*')

    # Upload limits (P0 Security)
    # Maximum file size: 10 GB (genomic FASTQ files can be large)
    MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 10 * 1024 * 1024 * 1024))  # 10 GB default
    # Maximum number of files per upload
    MAX_UPLOAD_FILES = int(os.getenv('MAX_UPLOAD_FILES', 10))
    # Allowed file extensions for FASTQ uploads
    ALLOWED_EXTENSIONS = os.getenv('ALLOWED_EXTENSIONS', '.fastq,.fastq.gz,.fq,.fq.gz').split(',')


# Singleton instance
config = Config()

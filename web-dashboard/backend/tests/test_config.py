"""
Tests for Configuration Module
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os


class TestConfigClass:
    """Tests for Config class"""

    def test_config_exists(self):
        """Test config singleton exists"""
        from config import config
        assert config is not None

    def test_config_postgres_host_default(self):
        """Test default Postgres host"""
        from config import config
        assert config.POSTGRES_HOST == os.getenv('POSTGRES_HOST', 'postgres')

    def test_config_postgres_port_default(self):
        """Test default Postgres port"""
        from config import config
        assert isinstance(config.POSTGRES_PORT, int)

    def test_config_postgres_db(self):
        """Test Postgres database name"""
        from config import config
        assert config.POSTGRES_DB is not None

    def test_config_redis_host_default(self):
        """Test default Redis host"""
        from config import config
        assert config.REDIS_HOST == os.getenv('REDIS_HOST', 'redis')

    def test_config_redis_port_default(self):
        """Test default Redis port"""
        from config import config
        assert isinstance(config.REDIS_PORT, int)


class TestConfigSecrets:
    """Tests for _require_secret (Docker secret file first, then environment)"""

    def test_reads_docker_secret_file(self, tmp_path):
        """Test a Docker secret file wins over the environment"""
        from config import _require_secret

        secret = tmp_path / 'test_secret'
        secret.write_text('file_value\n')

        with patch('config.Path', lambda p: secret if p == '/run/secrets/test_secret' else Path(p)), \
             patch.dict(os.environ, {'TEST_SECRET': 'env_value'}):
            assert _require_secret('test_secret', 'TEST_SECRET') == 'file_value'

    @patch.dict(os.environ, {'TEST_SECRET': 'env_value'})
    def test_falls_back_to_env(self):
        """Test the environment variable is used without a secret file"""
        from config import _require_secret

        assert _require_secret('no_such_secret_file', 'TEST_SECRET') == 'env_value'

    def test_missing_secret_exits(self):
        """Test a missing secret stops the process instead of using a default"""
        from config import _require_secret

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('TEST_SECRET_MISSING', None)
            with pytest.raises(SystemExit):
                _require_secret('no_such_secret_file', 'TEST_SECRET_MISSING')


class TestConfigMinio:
    """Tests for MinIO configuration"""

    def test_minio_endpoint(self):
        """Test MinIO endpoint"""
        from config import config
        assert config.MINIO_ENDPOINT is not None

    def test_minio_external_endpoint(self):
        """Test MinIO external endpoint"""
        from config import config
        assert config.MINIO_EXTERNAL_ENDPOINT is not None

    def test_minio_root_user(self):
        """Test MinIO root user"""
        from config import config
        assert config.MINIO_ROOT_USER is not None

    def test_minio_secure_boolean(self):
        """Test MinIO secure is boolean"""
        from config import config
        assert isinstance(config.MINIO_SECURE, bool)


class TestConfigPaths:
    """Tests for path configurations"""

    def test_nextflow_dir_is_path(self):
        """Test NEXTFLOW_DIR is a Path"""
        from config import config
        assert isinstance(config.NEXTFLOW_DIR, Path)

    def test_results_dir_is_path(self):
        """Test RESULTS_DIR is a Path"""
        from config import config
        assert isinstance(config.RESULTS_DIR, Path)

    def test_data_dir_is_path(self):
        """Test DATA_DIR is a Path"""
        from config import config
        assert isinstance(config.DATA_DIR, Path)

    def test_work_dir_is_path(self):
        """Test WORK_DIR is a Path"""
        from config import config
        assert isinstance(config.WORK_DIR, Path)


class TestConfigSanic:
    """Tests for Sanic configuration"""

    def test_sanic_port_is_int(self):
        """Test Sanic port is integer"""
        from config import config
        assert isinstance(config.SANIC_PORT, int)

    def test_sanic_debug_is_bool(self):
        """Test Sanic debug is boolean"""
        from config import config
        assert isinstance(config.SANIC_DEBUG, bool)

    def test_sanic_auto_reload_is_bool(self):
        """Test Sanic auto_reload is boolean"""
        from config import config
        assert isinstance(config.SANIC_AUTO_RELOAD, bool)


class TestConfigRedisQueue:
    """Tests for Redis Queue configuration"""

    def test_rq_queue_name(self):
        """Test RQ queue name"""
        from config import config
        assert config.RQ_QUEUE_NAME is not None

    def test_rq_job_timeout_is_int(self):
        """Test RQ job timeout is integer"""
        from config import config
        assert isinstance(config.RQ_JOB_TIMEOUT, int)


class TestConfigUploadLimits:
    """Tests for upload limit configuration"""

    def test_max_upload_size_is_int(self):
        """Test max upload size is integer"""
        from config import config
        assert isinstance(config.MAX_UPLOAD_SIZE, int)

    def test_max_upload_files_is_int(self):
        """Test max upload files is integer"""
        from config import config
        assert isinstance(config.MAX_UPLOAD_FILES, int)

    def test_allowed_extensions_is_list(self):
        """Test allowed extensions is list"""
        from config import config
        assert isinstance(config.ALLOWED_EXTENSIONS, list)

    def test_allowed_extensions_contains_fastq(self):
        """Test allowed extensions contains FASTQ extensions"""
        from config import config
        assert '.fastq' in config.ALLOWED_EXTENSIONS or '.fastq.gz' in config.ALLOWED_EXTENSIONS


class TestConfigDatabaseURL:
    """Tests for DATABASE_URL property"""

    def test_database_url_is_string(self):
        """Test DATABASE_URL is string"""
        from config import config
        assert isinstance(config.DATABASE_URL, str)

    def test_database_url_contains_postgresql(self):
        """Test DATABASE_URL contains postgresql"""
        from config import config
        assert 'postgresql://' in config.DATABASE_URL

    def test_database_url_contains_host(self):
        """Test DATABASE_URL contains host"""
        from config import config
        assert config.POSTGRES_HOST in config.DATABASE_URL


class TestConfigRedisURL:
    """Tests for REDIS_URL property"""

    def test_redis_url_is_string(self):
        """Test REDIS_URL is string"""
        from config import config
        assert isinstance(config.REDIS_URL, str)

    def test_redis_url_contains_redis(self):
        """Test REDIS_URL contains redis protocol"""
        from config import config
        assert 'redis://' in config.REDIS_URL

    def test_redis_url_contains_host(self):
        """Test REDIS_URL contains host"""
        from config import config
        assert config.REDIS_HOST in config.REDIS_URL

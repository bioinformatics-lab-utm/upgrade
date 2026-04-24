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
    """Tests for secret handling"""

    def test_get_secret_static_method(self):
        """Test get_secret is a static method"""
        from config import Config
        assert callable(Config.get_secret)

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_get_secret_from_file(self, mock_read, mock_exists):
        """Test reading secret from Docker secret file"""
        from config import Config
        
        mock_exists.return_value = True
        mock_read.return_value = 'secret_value\n'
        
        result = Config.get_secret('test_secret')
        
        assert result == 'secret_value'

    @patch('pathlib.Path.exists')
    @patch.dict(os.environ, {'TEST_SECRET': 'env_value'})
    def test_get_secret_from_env(self, mock_exists):
        """Test fallback to environment variable"""
        from config import Config
        
        mock_exists.return_value = False
        
        result = Config.get_secret('test_secret')
        
        assert result == 'env_value'

    @patch('pathlib.Path.exists')
    def test_get_secret_default(self, mock_exists):
        """Test default value when secret not found"""
        from config import Config
        
        mock_exists.return_value = False
        
        result = Config.get_secret('nonexistent_secret', 'default_value')
        
        assert result == 'default_value'


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

"""
Pytest configuration and fixtures for UPGRADE project tests
Comprehensive fixtures for unit testing without external dependencies
"""
import pytest
import pytest_asyncio
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import shutil
from datetime import date, datetime
import json

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================
# Mock Database Connection Fixtures
# ============================================

@pytest.fixture
def mock_db_pool():
    """Create a mock database connection pool"""
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    pool.release = AsyncMock()
    pool.close = AsyncMock()
    
    # Mock connection
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=1)
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock()
    mock_conn.executemany = AsyncMock()
    mock_conn.transaction = MagicMock()
    
    # Context manager for acquire
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    
    return pool


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection"""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=1)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    conn.close = AsyncMock()
    
    # Mock transaction context manager
    transaction = AsyncMock()
    transaction.__aenter__ = AsyncMock()
    transaction.__aexit__ = AsyncMock()
    conn.transaction.return_value = transaction
    
    return conn


# ============================================
# Sanic App and Request Fixtures
# ============================================

@pytest.fixture
def mock_sanic_app(mock_db_pool):
    """Create a mock Sanic application with all context"""
    app = Mock()
    app.ctx = Mock()
    app.ctx.db_pool = mock_db_pool
    app.ctx.redis = AsyncMock()
    app.ctx.minio_client = Mock()
    app.config = Mock()
    app.config.JWT_SECRET = "test-secret-key-for-testing"
    return app


@pytest.fixture
def mock_request(mock_sanic_app):
    """Create a mock Sanic request"""
    request = Mock()
    request.app = mock_sanic_app
    request.args = {}
    request.json = {}
    request.headers = {"Authorization": "Bearer test-token"}
    request.ctx = Mock()
    request.ctx.user = None
    request.remote_addr = "127.0.0.1"
    request.method = "GET"
    request.path = "/test"
    request.form = {}
    request.files = {}
    return request


@pytest.fixture
def authenticated_request(mock_request):
    """Create an authenticated mock request"""
    mock_request.ctx.user = {
        "user_id": 1,
        "username": "test_user",
        "email": "test@example.com",
        "role": "admin"
    }
    return mock_request


# ============================================
# MinIO Mock Fixtures
# ============================================

@pytest.fixture
def mock_minio_client():
    """Mock MinIO client"""
    client = Mock()
    client.bucket_exists = Mock(return_value=True)
    client.make_bucket = Mock()
    client.list_objects = Mock(return_value=[])
    client.put_object = Mock()
    client.get_object = Mock()
    client.remove_object = Mock()
    client.fget_object = Mock()
    client.fput_object = Mock()
    client.stat_object = Mock()
    client.presigned_get_object = Mock(return_value="http://test-presigned-url")
    client.presigned_put_object = Mock(return_value="http://test-presigned-url")
    return client


@pytest.fixture
def mock_minio_helper(mock_minio_client):
    """Mock MinIOHelper class"""
    helper = Mock()
    helper.client = mock_minio_client
    helper.upload_file = AsyncMock(return_value="test-object-key")
    helper.download_file = AsyncMock(return_value=b"test-content")
    helper.delete_file = AsyncMock(return_value=True)
    helper.list_files = AsyncMock(return_value=[])
    helper.get_presigned_url = AsyncMock(return_value="http://test-presigned-url")
    helper.bucket_exists = Mock(return_value=True)
    return helper


# ============================================
# Redis Mock Fixtures
# ============================================

@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.exists = AsyncMock(return_value=0)
    redis.ttl = AsyncMock(return_value=-1)
    redis.keys = AsyncMock(return_value=[])
    redis.ping = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_rq_queue():
    """Mock Redis Queue"""
    queue = Mock()
    mock_job = Mock()
    mock_job.id = 'test-job-123'
    mock_job.get_status = Mock(return_value='queued')
    mock_job.result = None
    queue.enqueue = Mock(return_value=mock_job)
    queue.fetch_job = Mock(return_value=mock_job)
    queue.count = 0
    return queue


# ============================================
# File System Fixtures
# ============================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory"""
    temp = tempfile.mkdtemp(prefix='test_')
    yield Path(temp)
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def temp_results_dir(temp_dir):
    """Create temporary results directory structure"""
    results = temp_dir / "results"
    results.mkdir()
    (results / "00_summary").mkdir()
    (results / "01_qc").mkdir()
    (results / "02_assembly").mkdir()
    return results


@pytest.fixture
def sample_fastq_file(temp_dir):
    """Create a sample FASTQ file"""
    fastq_path = temp_dir / "test.fastq"
    fastq_content = """@SEQ_ID_1
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65
@SEQ_ID_2
CCCTTCTTGTCTTCAGCGTTTCTCC
+
IIIIIIIIIIIIIIIIIIIIIIIII
"""
    fastq_path.write_text(fastq_content)
    return fastq_path


@pytest.fixture
def sample_fastq_gz_file(temp_dir):
    """Create a gzipped sample FASTQ file"""
    import gzip
    fastq_path = temp_dir / "test.fastq.gz"
    fastq_content = b"""@SEQ_ID_1
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65
@SEQ_ID_2
CCCTTCTTGTCTTCAGCGTTTCTCC
+
IIIIIIIIIIIIIIIIIIIIIIIII
"""
    with gzip.open(fastq_path, 'wb') as f:
        f.write(fastq_content)
    return fastq_path


# ============================================
# Sample Data Fixtures
# ============================================

@pytest.fixture
def sample_summary_data():
    """Sample pipeline summary JSON data"""
    return {
        "sample_id": "TEST_SAMPLE_001",
        "pipeline_version": "2.0.0",
        "quality_score": 42.5,
        "amr_risk_score": 3,
        "qc": {
            "total_reads": 100000,
            "total_bases": 500000000,
            "mean_quality": 12.5
        },
        "assembly": {
            "total_contigs": 150,
            "total_length": 4500000,
            "n50": 35000
        },
        "mags": {
            "total_bins": 25,
            "high_quality": 8,
            "medium_quality": 10,
            "low_quality": 7,
            "bins": []
        },
        "taxonomy": {
            "classified_reads": 85000
        },
        "amr": {
            "total_arg_genes": 12,
            "high_risk": 3,
            "moderate_risk": 9,
            "risk_score": 3,
            "genes": []
        },
        "functional": {},
        "viruses": {},
        "plasmids": {},
        "pathogens": [
            {
                "name": "Escherichia coli",
                "confidence": 0.95
            }
        ],
        "recommendations": []
    }


@pytest.fixture
def sample_summary_file(temp_results_dir, sample_summary_data):
    """Create a sample summary JSON file"""
    summary_path = temp_results_dir / "00_summary" / "test_summary.json"
    summary_path.write_text(json.dumps(sample_summary_data, indent=2))
    return summary_path


@pytest.fixture
def sample_user_data():
    """Sample user registration data"""
    return {
        "username": "test_user",
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User",
        "user_type": "researcher"
    }


@pytest.fixture
def sample_user_record():
    """Mock user database record"""
    return {
        "user_id": 1,
        "username": "test_user",
        "email": "test@example.com",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.pFtr.6y7vA9L1e",  # "password123"
        "first_name": "Test",
        "last_name": "User",
        "user_type": "researcher",
        "is_active": True,
        "created_at": datetime(2025, 1, 1, 0, 0, 0),
        "updated_at": datetime(2025, 1, 1, 0, 0, 0),
    }


@pytest.fixture
def sample_pipeline_params():
    """Sample pipeline parameters"""
    return {
        "sample_code": "TEST_SAMPLE_001",
        "input_dir": "/data/test_sample",
        "outdir": "/results/test_sample",
        "threads": 4,
        "memory": "8GB",
        "filtlong_min_length": 1000,
        "flye_genome_size": "5m"
    }


@pytest.fixture
def sample_record():
    """Mock sample database record"""
    return {
        "sample_id": 1,
        "sample_code": "TEST_SAMPLE_001",
        "sample_type": "nanopore",
        "sequencing_platform": "Oxford Nanopore",
        "collection_date": date(2025, 1, 1),
        "latitude": 48.8566,
        "longitude": 2.3522,
        "location_name": "Paris, France",
        "created_at": datetime(2025, 1, 1, 0, 0, 0),
        "updated_at": datetime(2025, 1, 1, 0, 0, 0),
    }


@pytest.fixture
def pipeline_run_record():
    """Mock pipeline run database record"""
    return {
        "pipeline_id": 1,
        "sample_id": 1,
        "pipeline_name": "nextflow_pipeline",
        "pipeline_version": "2.0.0",
        "status": "completed",
        "results_path": "/results/test_sample",
        "started_at": datetime(2025, 1, 1, 10, 0, 0),
        "completed_at": datetime(2025, 1, 1, 11, 0, 0),
        "created_at": datetime(2025, 1, 1, 10, 0, 0),
        "error_message": None,
    }


# ============================================
# Environment Fixtures
# ============================================

@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables"""
    env_vars = {
        "JWT_SECRET": "test-jwt-secret-key-very-secure",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test_db",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test_password",
        "MINIO_ENDPOINT": "localhost:9000",
        "MINIO_ACCESS_KEY": "test_access_key",
        "MINIO_SECRET_KEY": "test_secret_key",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "REDIS_PASSWORD": "test_redis_password",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


# ============================================
# Async Test Helpers
# ============================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ============================================
# Service Mocks
# ============================================

@pytest.fixture
def mock_sample_service(mock_db_pool):
    """Mock SampleService"""
    service = Mock()
    service.get_sample = AsyncMock(return_value=None)
    service.get_samples = AsyncMock(return_value=[])
    service.create_sample = AsyncMock(return_value=1)
    service.update_sample = AsyncMock(return_value=True)
    service.delete_sample = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_pipeline_service(mock_db_pool):
    """Mock PipelineService"""
    service = Mock()
    service.get_pipeline_run = AsyncMock(return_value=None)
    service.get_pipeline_runs = AsyncMock(return_value=[])
    service.create_pipeline_run = AsyncMock(return_value=1)
    service.update_pipeline_status = AsyncMock(return_value=True)
    service.start_pipeline = AsyncMock(return_value="job-id-123")
    return service


# ============================================
# Repository Mocks
# ============================================

@pytest.fixture
def mock_user_repository(mock_db_pool):
    """Mock UserRepository"""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_username = AsyncMock(return_value=None)
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=1)
    repo.update = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_sample_repository(mock_db_pool):
    """Mock SampleRepository"""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_code = AsyncMock(return_value=None)
    repo.get_all = AsyncMock(return_value=[])
    repo.create = AsyncMock(return_value=1)
    repo.update = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mock_pipeline_repository(mock_db_pool):
    """Mock PipelineRepository"""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_sample_id = AsyncMock(return_value=[])
    repo.get_all = AsyncMock(return_value=[])
    repo.create = AsyncMock(return_value=1)
    repo.update_status = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    return repo


# ============================================
# Markers Configuration
# ============================================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (require external services)")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_db: Tests requiring database connection")
    config.addinivalue_line("markers", "requires_minio: Tests requiring MinIO")
    config.addinivalue_line("markers", "requires_redis: Tests requiring Redis")

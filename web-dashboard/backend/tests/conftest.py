"""
Pytest configuration and fixtures for UPGRADE project tests
"""
import pytest
import asyncio
import asyncpg
import os
from unittest.mock import Mock, AsyncMock, MagicMock
from pathlib import Path
import tempfile
import shutil

# Test database configuration
TEST_DB_CONFIG = {
    'host': os.getenv('TEST_DB_HOST', 'localhost'),
    'port': int(os.getenv('TEST_DB_PORT', 5432)),
    'database': os.getenv('TEST_DB_NAME', 'upgrade_test_db'),
    'user': os.getenv('TEST_DB_USER', 'upgrade'),
    'password': os.getenv('TEST_DB_PASSWORD', 'upgrade')
}


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_pool():
    """Create test database connection pool"""
    pool = await asyncpg.create_pool(**TEST_DB_CONFIG, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn(db_pool):
    """Get single database connection"""
    async with db_pool.acquire() as conn:
        yield conn


@pytest.fixture
async def clean_db(db_conn):
    """Clean database before each test"""
    # Truncate test tables
    await db_conn.execute("TRUNCATE TABLE pipeline_runs CASCADE")
    await db_conn.execute("TRUNCATE TABLE samples CASCADE")
    await db_conn.execute("TRUNCATE TABLE users CASCADE")
    yield db_conn


@pytest.fixture
def temp_results_dir():
    """Create temporary results directory"""
    temp_dir = tempfile.mkdtemp(prefix='test_results_')
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


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
def mock_minio_client():
    """Mock MinIO client"""
    client = Mock()
    client.bucket_exists = Mock(return_value=True)
    client.make_bucket = Mock()
    client.list_objects = Mock(return_value=[])
    client.put_object = Mock()
    client.get_object = Mock()
    client.remove_object = Mock()
    return client


@pytest.fixture
def mock_sanic_app():
    """Mock Sanic application"""
    app = Mock()
    app.ctx = Mock()
    app.ctx.db_pool = AsyncMock()
    return app


@pytest.fixture
def mock_request():
    """Mock Sanic request"""
    request = Mock()
    request.app = mock_sanic_app()
    request.args = {}
    request.json = {}
    request.headers = {}
    request.ctx = Mock()
    request.ctx.user = None
    return request


@pytest.fixture
def sample_fastq_content():
    """Sample FASTQ file content"""
    return """@SEQ_ID_1
GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT
+
!''*((((***+))%%%++)(%%%%).1***-+*''))**55CCF>>>>>>CCCCCCC65
@SEQ_ID_2
CCCTTCTTGTCTTCAGCGTTTCTCC
+
IIIIIIIIIIIIIIIIIIIIIIIII
"""


@pytest.fixture
def sample_user_data():
    """Sample user registration data"""
    return {
        "username": "test_user",
        "email": "test@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User",
        "organization": "Test Lab"
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
async def test_sample(db_conn):
    """Create test sample in database"""
    sample_id = await db_conn.fetchval("""
        INSERT INTO samples (
            sample_code, sample_type, sequencing_platform,
            collection_date, created_at
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING sample_id
    """, 'TEST_SAMPLE_001', 'nanopore', 'Oxford Nanopore',
        '2025-12-24', '2025-12-24 10:00:00')
    
    yield sample_id
    
    # Cleanup
    await db_conn.execute("DELETE FROM samples WHERE sample_id = $1", sample_id)


@pytest.fixture
async def test_pipeline_run(db_conn, test_sample):
    """Create test pipeline run in database"""
    pipeline_id = await db_conn.fetchval("""
        INSERT INTO pipeline_runs (
            sample_id, pipeline_name, pipeline_version,
            status, results_path, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING pipeline_id
    """, test_sample, 'nextflow_pipeline', '2.0.0',
        'completed', '/results/test_sample', '2025-12-24 10:00:00')
    
    yield pipeline_id
    
    # Cleanup
    await db_conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id)


@pytest.fixture
def mock_redis_queue():
    """Mock Redis Queue"""
    queue = Mock()
    queue.enqueue = Mock(return_value=Mock(id='test-job-123'))
    queue.fetch_job = Mock()
    return queue


# Markers
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_db: Tests requiring database connection")
    config.addinivalue_line("markers", "requires_minio: Tests requiring MinIO")

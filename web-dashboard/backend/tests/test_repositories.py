"""
Tests for BaseRepository and derived repositories
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime
from contextlib import asynccontextmanager


def create_mock_pool():
    """Create a properly configured mock database pool"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock()
    mock_conn.fetchval = AsyncMock()
    mock_conn.fetch = AsyncMock()
    mock_conn.execute = AsyncMock()
    
    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn
    
    pool = MagicMock()
    pool.acquire = mock_acquire
    
    return pool, mock_conn


class TestBaseRepository:
    """Tests for BaseRepository class"""

    @pytest.fixture
    def mock_pool(self):
        """Create mock database pool"""
        return create_mock_pool()

    @pytest.mark.asyncio
    async def test_init(self, mock_pool):
        """Test repository initialization"""
        pool, _ = mock_pool
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        assert repo.pool == pool

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_pool):
        """Test find_by_id method"""
        pool, mock_conn = mock_pool
        
        expected_result = {"sample_id": 1, "sample_code": "TEST001"}
        mock_conn.fetchrow.return_value = expected_result
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        result = await repo.find_by_id(1)
        
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, mock_pool):
        """Test find_by_id returns None when not found"""
        pool, mock_conn = mock_pool
        mock_conn.fetchrow.return_value = None
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        result = await repo.find_by_id(999)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_find_all(self, mock_pool):
        """Test find_all method"""
        pool, mock_conn = mock_pool
        
        expected_results = [
            {"sample_id": 1, "sample_code": "TEST001"},
            {"sample_id": 2, "sample_code": "TEST002"}
        ]
        mock_conn.fetch.return_value = expected_results
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        result = await repo.find_all(limit=10, offset=0)
        
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_count(self, mock_pool):
        """Test count method"""
        pool, mock_conn = mock_pool
        mock_conn.fetchval.return_value = 42
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        result = await repo.count()
        
        assert result == 42

    @pytest.mark.asyncio
    async def test_exists(self, mock_pool):
        """Test exists method"""
        pool, mock_conn = mock_pool
        mock_conn.fetchval.return_value = True
        
        from repositories.sample_repository import SampleRepository
        repo = SampleRepository(pool)
        result = await repo.exists("sample_code = $1", ("TEST001",))
        
        assert result is True


class TestUserRepository:
    """Tests for UserRepository class"""

    @pytest.fixture
    def mock_pool(self):
        """Create mock database pool"""
        return create_mock_pool()

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_pool):
        """Test find user by ID"""
        from repositories.user_repository import UserRepository
        pool, mock_conn = mock_pool
        
        expected_user = {
            "user_id": 1,
            "username": "testuser",
            "email": "test@test.com"
        }
        mock_conn.fetchrow.return_value = expected_user
        
        repo = UserRepository(pool)
        result = await repo.find_by_id(1)
        
        assert result == expected_user

    @pytest.mark.asyncio
    async def test_find_by_username(self, mock_pool):
        """Test find user by username"""
        from repositories.user_repository import UserRepository
        pool, mock_conn = mock_pool
        
        expected_user = {
            "user_id": 1,
            "username": "testuser",
            "email": "test@test.com"
        }
        mock_conn.fetchrow.return_value = expected_user
        
        repo = UserRepository(pool)
        result = await repo.find_by_username("testuser")
        
        assert result == expected_user

    @pytest.mark.asyncio
    async def test_find_by_email(self, mock_pool):
        """Test find user by email"""
        from repositories.user_repository import UserRepository
        pool, mock_conn = mock_pool
        
        expected_user = {
            "user_id": 1,
            "username": "testuser",
            "email": "test@test.com"
        }
        mock_conn.fetchrow.return_value = expected_user
        
        repo = UserRepository(pool)
        result = await repo.find_by_email("test@test.com")
        
        assert result == expected_user

    @pytest.mark.asyncio
    async def test_create(self, mock_pool):
        """Test create user"""
        from repositories.user_repository import UserRepository
        from models.user import UserCreate
        pool, mock_conn = mock_pool
        
        mock_conn.fetchval.return_value = 1
        
        user_data = UserCreate(
            username="newuser",
            email="new@test.com",
            password="secure_password123",
            full_name="New User"
        )
        
        repo = UserRepository(pool)
        result = await repo.create(user_data, password_hash="hashed_password")
        
        assert result == 1


class TestSampleRepository:
    """Tests for SampleRepository class"""

    @pytest.fixture
    def mock_pool(self):
        """Create mock database pool"""
        return create_mock_pool()

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_pool):
        """Test find sample by ID"""
        from repositories.sample_repository import SampleRepository
        pool, mock_conn = mock_pool
        
        expected_sample = {
            "sample_id": 1,
            "sample_code": "TEST001",
            "sample_type": "nanopore"
        }
        mock_conn.fetchrow.return_value = expected_sample
        
        repo = SampleRepository(pool)
        result = await repo.find_by_id(1)
        
        assert result == expected_sample

    @pytest.mark.asyncio
    async def test_find_by_code(self, mock_pool):
        """Test find sample by code"""
        from repositories.sample_repository import SampleRepository
        pool, mock_conn = mock_pool
        
        expected_sample = {
            "sample_id": 1,
            "sample_code": "TEST001",
            "sample_type": "nanopore"
        }
        mock_conn.fetchrow.return_value = expected_sample
        
        repo = SampleRepository(pool)
        result = await repo.find_by_code("TEST001")
        
        assert result == expected_sample

    @pytest.mark.asyncio
    async def test_find_all(self, mock_pool):
        """Test find all samples"""
        from repositories.sample_repository import SampleRepository
        pool, mock_conn = mock_pool
        
        expected_samples = [
            {"sample_id": 1, "sample_code": "TEST001"},
            {"sample_id": 2, "sample_code": "TEST002"}
        ]
        mock_conn.fetch.return_value = expected_samples
        
        repo = SampleRepository(pool)
        result = await repo.find_all()
        
        assert len(result) == 2


class TestPipelineRepository:
    """Tests for PipelineRepository class"""

    @pytest.fixture
    def mock_pool(self):
        """Create mock database pool"""
        return create_mock_pool()

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_pool):
        """Test find pipeline by ID"""
        from repositories.pipeline_repository import PipelineRepository
        pool, mock_conn = mock_pool
        
        expected_run = {
            "pipeline_id": 1,
            "sample_id": 1,
            "status": "completed"
        }
        mock_conn.fetchrow.return_value = expected_run
        
        repo = PipelineRepository(pool)
        result = await repo.find_by_id(1)
        
        assert result == expected_run

    @pytest.mark.asyncio
    async def test_find_by_sample_id(self, mock_pool):
        """Test find pipeline runs by sample ID"""
        from repositories.pipeline_repository import PipelineRepository
        pool, mock_conn = mock_pool
        
        expected_runs = [
            {"pipeline_id": 1, "status": "completed"},
            {"pipeline_id": 2, "status": "running"}
        ]
        mock_conn.fetch.return_value = expected_runs
        
        repo = PipelineRepository(pool)
        result = await repo.find_by_sample(1)
        
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_create(self, mock_pool):
        """Test create pipeline run"""
        from repositories.pipeline_repository import PipelineRepository
        from models.pipeline_run import PipelineRunCreate
        pool, mock_conn = mock_pool
        
        mock_conn.fetchval.return_value = 1
        
        run_data = PipelineRunCreate(
            sample_id=1,
            sample_name="SAMPLE001",
            pipeline_name="nextflow_pipeline",
            pipeline_version="2.0"
        )
        
        repo = PipelineRepository(pool)
        result = await repo.create(run_data)
        
        assert result == 1

    @pytest.mark.asyncio
    async def test_update_status(self, mock_pool):
        """Test update pipeline status"""
        from repositories.pipeline_repository import PipelineRepository
        from models.pipeline_run import PipelineRunUpdate
        pool, mock_conn = mock_pool
        
        mock_conn.fetchval.return_value = 1
        mock_conn.execute.return_value = "UPDATE 1"
        
        update_data = PipelineRunUpdate(status="completed")
        
        repo = PipelineRepository(pool)
        await repo.update(1, update_data)
        
        # Test passes if no exception raised

    @pytest.mark.asyncio
    async def test_find_all(self, mock_pool):
        """Test find all pipeline runs"""
        from repositories.pipeline_repository import PipelineRepository
        pool, mock_conn = mock_pool
        
        expected_runs = [
            {"pipeline_id": 1, "status": "completed", "parameters": "{}"},
            {"pipeline_id": 2, "status": "running", "parameters": "{}"}
        ]
        mock_conn.fetch.return_value = expected_runs
        
        repo = PipelineRepository(pool)
        result = await repo.find_all()
        
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_active_for_sample(self, mock_pool):
        """Test finding active pipelines for a sample"""
        from repositories.pipeline_repository import PipelineRepository
        pool, mock_conn = mock_pool
        
        expected_run = {
            "pipeline_id": 1,
            "status": "running",
            "parameters": "{}"
        }
        mock_conn.fetchrow.return_value = expected_run
        
        repo = PipelineRepository(pool)
        result = await repo.find_active_for_sample(1)
        
        assert result is not None
        assert result['status'] == 'running'
"""
Tests for Pipeline Service
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime


class TestPipelineServiceInit:
    """Tests for PipelineService initialization"""

    def test_init_with_repos(self):
        """Test PipelineService initialization with repositories"""
        from services.pipeline_service import PipelineService
        
        mock_pipeline_repo = Mock()
        mock_sample_repo = Mock()
        
        service = PipelineService(
            pipeline_repo=mock_pipeline_repo,
            sample_repo=mock_sample_repo
        )
        
        assert service.pipeline_repo == mock_pipeline_repo
        assert service.sample_repo == mock_sample_repo

    def test_init_with_optional_services(self):
        """Test PipelineService with optional services"""
        from services.pipeline_service import PipelineService
        
        mock_pipeline_repo = Mock()
        mock_sample_repo = Mock()
        mock_sample_service = Mock()
        mock_storage_service = Mock()
        
        service = PipelineService(
            pipeline_repo=mock_pipeline_repo,
            sample_repo=mock_sample_repo,
            sample_service=mock_sample_service,
            storage_service=mock_storage_service
        )
        
        assert service.sample_service == mock_sample_service
        assert service.storage_service == mock_storage_service


class TestPipelineServiceCreateRun:
    """Tests for create_pipeline_run method"""

    @pytest.fixture
    def service_with_mocks(self):
        """Create service with mock repositories"""
        from services.pipeline_service import PipelineService
        
        mock_pipeline_repo = AsyncMock()
        mock_sample_repo = AsyncMock()
        
        service = PipelineService(
            pipeline_repo=mock_pipeline_repo,
            sample_repo=mock_sample_repo
        )
        
        return service, mock_pipeline_repo, mock_sample_repo

    @pytest.mark.asyncio
    async def test_create_pipeline_run_success(self, service_with_mocks):
        """Test successful pipeline run creation"""
        from models.pipeline_run import PipelineRunCreate
        
        service, pipeline_repo, sample_repo = service_with_mocks
        
        # Sample exists
        sample_repo.find_by_id.return_value = {"sample_id": 1, "sample_code": "S001"}
        # No active pipeline
        pipeline_repo.find_active_for_sample.return_value = None
        # Create returns ID
        pipeline_repo.create.return_value = 42
        
        run_data = PipelineRunCreate(
            sample_id=1,
            pipeline_name="test_pipeline",
            sample_name="S001"
        )
        
        result = await service.create_pipeline_run(run_data)
        
        assert result == 42
        pipeline_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pipeline_run_sample_not_found(self, service_with_mocks):
        """Test create fails when sample not found"""
        from models.pipeline_run import PipelineRunCreate
        
        service, pipeline_repo, sample_repo = service_with_mocks
        
        # Sample does not exist
        sample_repo.find_by_id.return_value = None
        
        run_data = PipelineRunCreate(
            sample_id=999,
            pipeline_name="test_pipeline"
        )
        
        with pytest.raises(ValueError) as exc_info:
            await service.create_pipeline_run(run_data)
        
        assert "Sample" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_pipeline_run_duplicate_blocked(self, service_with_mocks):
        """Test create blocked when active pipeline exists"""
        from models.pipeline_run import PipelineRunCreate
        
        service, pipeline_repo, sample_repo = service_with_mocks
        
        # Sample exists
        sample_repo.find_by_id.return_value = {"sample_id": 1}
        # Active pipeline exists
        pipeline_repo.find_active_for_sample.return_value = {
            "pipeline_id": 10,
            "status": "running"
        }
        
        run_data = PipelineRunCreate(
            sample_id=1,
            pipeline_name="test_pipeline"
        )
        
        with pytest.raises(ValueError):
            await service.create_pipeline_run(run_data)

    @pytest.mark.asyncio
    async def test_create_pipeline_run_allow_duplicate(self, service_with_mocks):
        """Test create allowed with allow_duplicate=True"""
        from models.pipeline_run import PipelineRunCreate
        
        service, pipeline_repo, sample_repo = service_with_mocks
        
        # Sample exists
        sample_repo.find_by_id.return_value = {"sample_id": 1, "sample_code": "S001"}
        # Active pipeline exists
        pipeline_repo.find_active_for_sample.return_value = {
            "pipeline_id": 10,
            "status": "running"
        }
        # Create returns ID
        pipeline_repo.create.return_value = 42
        
        run_data = PipelineRunCreate(
            sample_id=1,
            pipeline_name="test_pipeline",
            sample_name="S001"
        )
        
        result = await service.create_pipeline_run(run_data, allow_duplicate=True)
        
        assert result == 42


class TestPipelineServiceClass:
    """Tests for PipelineService class structure"""

    def test_pipeline_service_exists(self):
        """Test PipelineService class exists"""
        from services.pipeline_service import PipelineService
        assert PipelineService is not None

    def test_has_create_pipeline_run_method(self):
        """Test has create_pipeline_run method"""
        from services.pipeline_service import PipelineService
        assert hasattr(PipelineService, 'create_pipeline_run')

    def test_imports_models(self):
        """Test service imports required models"""
        from services.pipeline_service import PipelineRun, PipelineRunCreate
        assert PipelineRun is not None
        assert PipelineRunCreate is not None

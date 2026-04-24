"""
Tests for Sample Service
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import date


class TestSampleServiceInit:
    """Tests for SampleService initialization"""

    def test_init_with_repo(self):
        """Test SampleService initialization"""
        from services.sample_service import SampleService
        
        mock_repo = Mock()
        service = SampleService(mock_repo)
        
        assert service.sample_repo == mock_repo


class TestSampleServiceGetSample:
    """Tests for get_sample method"""

    @pytest.fixture
    def service_with_mock(self):
        """Create service with mock repo"""
        from services.sample_service import SampleService
        
        mock_repo = AsyncMock()
        return SampleService(mock_repo), mock_repo

    @pytest.mark.asyncio
    async def test_get_sample_found(self, service_with_mock):
        """Test getting sample by ID when found"""
        service, mock_repo = service_with_mock
        
        mock_repo.find_by_id.return_value = {
            "sample_id": 1,
            "sample_code": "S001",
            "collection_date": date(2024, 1, 15)
        }
        
        result = await service.get_sample(1)
        
        assert result is not None
        mock_repo.find_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_get_sample_not_found(self, service_with_mock):
        """Test getting sample by ID when not found"""
        service, mock_repo = service_with_mock
        
        mock_repo.find_by_id.return_value = None
        
        result = await service.get_sample(999)
        
        assert result is None


class TestSampleServiceGetSampleByCode:
    """Tests for get_sample_by_code method"""

    @pytest.fixture
    def service_with_mock(self):
        """Create service with mock repo"""
        from services.sample_service import SampleService
        
        mock_repo = AsyncMock()
        return SampleService(mock_repo), mock_repo

    @pytest.mark.asyncio
    async def test_get_sample_by_code_found(self, service_with_mock):
        """Test getting sample by code"""
        service, mock_repo = service_with_mock
        
        mock_repo.find_by_code.return_value = {
            "sample_id": 1,
            "sample_code": "S001",
            "collection_date": date(2024, 1, 15)
        }
        
        result = await service.get_sample_by_code("S001")
        
        assert result is not None


class TestSampleServiceCreateSample:
    """Tests for create_sample method"""

    @pytest.fixture
    def service_with_mock(self):
        """Create service with mock repo"""
        from services.sample_service import SampleService
        
        mock_repo = AsyncMock()
        return SampleService(mock_repo), mock_repo

    @pytest.mark.asyncio
    async def test_create_sample_success(self, service_with_mock):
        """Test creating sample successfully"""
        from models.sample import SampleCreate
        
        service, mock_repo = service_with_mock
        
        mock_repo.find_by_code.return_value = None  # Not duplicate
        mock_repo.create.return_value = 1
        
        sample_data = SampleCreate(
            sample_code="S002",
            collection_date=date(2024, 1, 15)
        )
        
        result = await service.create_sample(sample_data)
        
        assert result == 1
        mock_repo.create.assert_called_once()


class TestSampleServiceClass:
    """Tests for SampleService class structure"""

    def test_class_exists(self):
        """Test SampleService class exists"""
        from services.sample_service import SampleService
        assert SampleService is not None

    def test_has_get_sample_method(self):
        """Test has get_sample method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'get_sample')

    def test_has_get_sample_by_code_method(self):
        """Test has get_sample_by_code method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'get_sample_by_code')

    def test_has_create_sample_method(self):
        """Test has create_sample method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'create_sample')

    def test_has_update_sample_method(self):
        """Test has update_sample method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'update_sample')

    def test_has_delete_sample_method(self):
        """Test has delete_sample method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'delete_sample')

    def test_has_list_samples_method(self):
        """Test has list_samples method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'list_samples')

    def test_has_count_samples_method(self):
        """Test has count_samples method"""
        from services.sample_service import SampleService
        assert hasattr(SampleService, 'count_samples')

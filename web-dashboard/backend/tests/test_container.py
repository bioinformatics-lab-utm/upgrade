"""
Tests for Dependency Injection Container
"""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock


class TestServiceContainerImport:
    """Test ServiceContainer import"""

    def test_service_container_class_exists(self):
        """Test ServiceContainer class can be imported"""
        from container import ServiceContainer
        assert ServiceContainer is not None

    def test_create_service_container_exists(self):
        """Test create_service_container function exists"""
        from container import create_service_container
        assert create_service_container is not None


class TestServiceContainerInit:
    """Test ServiceContainer initialization"""

    def test_init_stores_db_pool(self):
        """Test init stores db_pool"""
        from container import ServiceContainer
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = ServiceContainer(mock_pool, mock_minio)
        
        assert container.db_pool == mock_pool

    def test_init_stores_minio_client(self):
        """Test init stores minio_client"""
        from container import ServiceContainer
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = ServiceContainer(mock_pool, mock_minio)
        
        assert container.minio_client == mock_minio

    def test_init_creates_sample_repo(self):
        """Test init creates sample repository"""
        from container import ServiceContainer
        from repositories.sample_repository import SampleRepository
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = ServiceContainer(mock_pool, mock_minio)
        
        assert container.sample_repo is not None
        assert isinstance(container.sample_repo, SampleRepository)

    def test_init_creates_pipeline_repo(self):
        """Test init creates pipeline repository"""
        from container import ServiceContainer
        from repositories.pipeline_repository import PipelineRepository
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = ServiceContainer(mock_pool, mock_minio)
        
        assert container.pipeline_repo is not None
        assert isinstance(container.pipeline_repo, PipelineRepository)

    def test_init_creates_user_repo(self):
        """Test init creates user repository"""
        from container import ServiceContainer
        from repositories.user_repository import UserRepository
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = ServiceContainer(mock_pool, mock_minio)
        
        assert container.user_repo is not None
        assert isinstance(container.user_repo, UserRepository)


class TestServiceContainerServices:
    """Test ServiceContainer services"""

    @pytest.fixture
    def container(self):
        """Create container fixture"""
        from container import ServiceContainer
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        return ServiceContainer(mock_pool, mock_minio)

    def test_init_creates_storage_service(self, container):
        """Test init creates storage service"""
        from services.storage_service import StorageService
        
        assert container.storage_service is not None
        assert isinstance(container.storage_service, StorageService)

    def test_init_creates_sample_service(self, container):
        """Test init creates sample service"""
        from services.sample_service import SampleService
        
        assert container.sample_service is not None
        assert isinstance(container.sample_service, SampleService)

    def test_init_creates_pipeline_service(self, container):
        """Test init creates pipeline service"""
        from services.pipeline_service import PipelineService
        
        assert container.pipeline_service is not None
        assert isinstance(container.pipeline_service, PipelineService)


class TestServiceContainerGetters:
    """Test ServiceContainer getter methods"""

    @pytest.fixture
    def container(self):
        """Create container fixture"""
        from container import ServiceContainer
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        return ServiceContainer(mock_pool, mock_minio)

    def test_get_sample_service(self, container):
        """Test get_sample_service returns service"""
        from services.sample_service import SampleService
        
        service = container.get_sample_service()
        
        assert service is not None
        assert isinstance(service, SampleService)
        assert service == container.sample_service

    def test_get_pipeline_service(self, container):
        """Test get_pipeline_service returns service"""
        from services.pipeline_service import PipelineService
        
        service = container.get_pipeline_service()
        
        assert service is not None
        assert isinstance(service, PipelineService)
        assert service == container.pipeline_service

    def test_get_storage_service(self, container):
        """Test get_storage_service returns service"""
        from services.storage_service import StorageService
        
        service = container.get_storage_service()
        
        assert service is not None
        assert isinstance(service, StorageService)
        assert service == container.storage_service


class TestCreateServiceContainer:
    """Test create_service_container factory"""

    def test_returns_service_container(self):
        """Test factory returns ServiceContainer instance"""
        from container import create_service_container, ServiceContainer
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = create_service_container(mock_pool, mock_minio)
        
        assert isinstance(container, ServiceContainer)

    def test_passes_dependencies_correctly(self):
        """Test factory passes dependencies to container"""
        from container import create_service_container
        
        mock_pool = Mock()
        mock_minio = Mock()
        
        container = create_service_container(mock_pool, mock_minio)
        
        assert container.db_pool == mock_pool
        assert container.minio_client == mock_minio

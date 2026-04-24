"""
Dependency Injection container for service initialization.
"""
import asyncpg
from minio import Minio

from repositories.sample_repository import SampleRepository
from repositories.pipeline_repository import PipelineRepository
from repositories.user_repository import UserRepository

from services.sample_service import SampleService
from services.pipeline_service import PipelineService
from services.storage_service import StorageService


class ServiceContainer:
    """
    Container for managing service dependencies.
    
    Provides centralized initialization and dependency injection
    for all services and repositories.
    """
    
    def __init__(self, db_pool: asyncpg.Pool, minio_client: Minio):
        """
        Initialize service container with infrastructure dependencies.
        
        Args:
            db_pool: Database connection pool
            minio_client: MinIO client instance
        """
        # Infrastructure
        self.db_pool = db_pool
        self.minio_client = minio_client
        
        # Repositories
        self.sample_repo = SampleRepository(db_pool)
        self.pipeline_repo = PipelineRepository(db_pool)
        self.user_repo = UserRepository(db_pool)
        
        # Services (with cross-dependencies)
        self.storage_service = StorageService(minio_client)
        self.sample_service = SampleService(self.sample_repo)
        self.pipeline_service = PipelineService(
            self.pipeline_repo,
            self.sample_repo,
            self.sample_service,
            self.storage_service
        )
    
    def get_sample_service(self) -> SampleService:
        """Get sample service instance."""
        return self.sample_service
    
    def get_pipeline_service(self) -> PipelineService:
        """Get pipeline service instance."""
        return self.pipeline_service
    
    def get_storage_service(self) -> StorageService:
        """Get storage service instance."""
        return self.storage_service


def create_service_container(
    db_pool: asyncpg.Pool,
    minio_client: Minio
) -> ServiceContainer:
    """
    Factory function to create a service container.
    
    Args:
        db_pool: Database connection pool
        minio_client: MinIO client instance
        
    Returns:
        Initialized ServiceContainer instance
    """
    return ServiceContainer(db_pool, minio_client)

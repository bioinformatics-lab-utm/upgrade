"""
Tests for Storage Service (MinIO)
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import timedelta


class TestStorageService:
    """Tests for StorageService class"""

    def test_init(self):
        """Test StorageService initialization"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        service = StorageService(mock_client)
        
        assert service.client is mock_client
        assert service.bronze_bucket == 'genomic-bronze'
        assert service.silver_bucket == 'genomic-silver'
        assert service.gold_bucket == 'genomic-gold'

    @pytest.mark.asyncio
    async def test_ensure_buckets_exist_creates_buckets(self):
        """Test ensure_buckets_exist creates missing buckets"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        mock_client.bucket_exists.return_value = False
        
        service = StorageService(mock_client)
        await service.ensure_buckets_exist()
        
        assert mock_client.bucket_exists.call_count == 3
        assert mock_client.make_bucket.call_count == 3

    @pytest.mark.asyncio
    async def test_ensure_buckets_exist_skips_existing(self):
        """Test ensure_buckets_exist skips existing buckets"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        mock_client.bucket_exists.return_value = True
        
        service = StorageService(mock_client)
        await service.ensure_buckets_exist()
        
        mock_client.make_bucket.assert_not_called()

    def test_generate_presigned_url(self):
        """Test generating presigned upload URL"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        mock_client.presigned_put_object.return_value = "https://minio.local/presigned"
        
        service = StorageService(mock_client)
        url = service.generate_presigned_url(
            bucket="genomic-bronze",
            object_path="samples/sample1.fastq"
        )
        
        assert url == "https://minio.local/presigned"
        mock_client.presigned_put_object.assert_called_once()

    def test_generate_presigned_url_with_expiry(self):
        """Test generating presigned URL with custom expiry"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        mock_client.presigned_put_object.return_value = "https://minio.local/presigned"
        
        service = StorageService(mock_client)
        url = service.generate_presigned_url(
            bucket="genomic-bronze",
            object_path="samples/sample1.fastq",
            expires=timedelta(hours=2)
        )
        
        call_args = mock_client.presigned_put_object.call_args
        assert call_args[0][2] == timedelta(hours=2)

    def test_generate_download_url(self):
        """Test generating download URL"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        mock_client.presigned_get_object.return_value = "https://minio.local/download"
        
        service = StorageService(mock_client)
        url = service.generate_download_url(
            bucket="genomic-silver",
            object_path="results/result1.json"
        )
        
        assert url == "https://minio.local/download"


class TestStorageServiceBuckets:
    """Tests for bucket operations"""

    def test_bucket_constants(self):
        """Test bucket name constants"""
        from services.storage_service import StorageService
        
        mock_client = Mock()
        service = StorageService(mock_client)
        
        assert 'bronze' in service.bronze_bucket
        assert 'silver' in service.silver_bucket
        assert 'gold' in service.gold_bucket


class TestStorageServiceErrorHandling:
    """Tests for error handling"""

    def test_presigned_url_error_handling(self):
        """Test error handling for presigned URL generation"""
        from services.storage_service import StorageService
        from minio.error import S3Error
        
        mock_client = Mock()
        mock_client.presigned_put_object.side_effect = S3Error(
            code="AccessDenied",
            message="Access denied",
            resource="bucket/object",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )
        
        service = StorageService(mock_client)
        
        with pytest.raises(S3Error):
            service.generate_presigned_url("bucket", "object")

    @pytest.mark.asyncio
    async def test_ensure_buckets_error_handling(self):
        """Test error handling for bucket creation"""
        from services.storage_service import StorageService
        from minio.error import S3Error
        
        mock_client = Mock()
        mock_client.bucket_exists.side_effect = S3Error(
            code="InternalError",
            message="Internal error",
            resource="bucket",
            request_id="req123",
            host_id="host123",
            response=Mock()
        )
        
        service = StorageService(mock_client)
        
        with pytest.raises(S3Error):
            await service.ensure_buckets_exist()

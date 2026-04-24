"""
Storage service for MinIO object storage operations.
"""
from typing import Optional, List, Dict, Any, BinaryIO
from datetime import timedelta
import logging
from pathlib import Path

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class StorageService:
    """
    Service for object storage operations using MinIO.
    
    Handles file uploads, downloads, and bucket management.
    """
    
    def __init__(self, minio_client: Minio):
        """
        Initialize service with MinIO client.
        
        Args:
            minio_client: MinIO client instance
        """
        self.client = minio_client
        self.bronze_bucket = 'genomic-bronze'
        self.silver_bucket = 'genomic-silver'
        self.gold_bucket = 'genomic-gold'
    
    async def ensure_buckets_exist(self) -> None:
        """
        Ensure all required buckets exist.
        
        Creates bronze, silver, and gold buckets if they don't exist.
        """
        for bucket in [self.bronze_bucket, self.silver_bucket, self.gold_bucket]:
            try:
                if not self.client.client.bucket_exists(bucket):
                    self.client.client.make_bucket(bucket)
                    logger.info(f"Created bucket: {bucket}")
            except S3Error as e:
                logger.error(f"Error ensuring bucket {bucket} exists: {e}")
                raise
    
    def generate_presigned_url(
        self,
        bucket: str,
        object_path: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate a presigned URL for uploading an object.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            expires: URL expiration time
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.client.client.presigned_put_object(bucket, object_path, expires)
            logger.debug(f"Generated presigned URL for {bucket}/{object_path}")
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise
    
    def generate_download_url(
        self,
        bucket: str,
        object_path: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate a presigned URL for downloading an object.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            expires: URL expiration time
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.client.client.presigned_get_object(bucket, object_path, expires)
            return url
        except S3Error as e:
            logger.error(f"Error generating download URL: {e}")
            raise
    
    def upload_file(
        self,
        bucket: str,
        object_path: str,
        file_path: str,
        content_type: str = 'application/octet-stream'
    ) -> None:
        """
        Upload a file to MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            file_path: Local file path
            content_type: MIME type of file
        """
        try:
            self.client.client.fput_object(
                bucket,
                object_path,
                file_path,
                content_type=content_type
            )
            logger.info(f"Uploaded {file_path} to {bucket}/{object_path}")
        except S3Error as e:
            logger.error(f"Error uploading file: {e}")
            raise
    
    def upload_data(
        self,
        bucket: str,
        object_path: str,
        data: BinaryIO,
        length: int,
        content_type: str = 'application/octet-stream'
    ) -> None:
        """
        Upload data from a file-like object to MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            data: File-like object with read() method
            length: Length of data in bytes
            content_type: MIME type
        """
        try:
            self.client.client.put_object(
                bucket,
                object_path,
                data,
                length,
                content_type=content_type
            )
            logger.info(f"Uploaded data to {bucket}/{object_path}")
        except S3Error as e:
            logger.error(f"Error uploading data: {e}")
            raise
    
    def download_file(
        self,
        bucket: str,
        object_path: str,
        file_path: str
    ) -> None:
        """
        Download a file from MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            file_path: Local destination file path
        """
        try:
            self.client.client.fget_object(bucket, object_path, file_path)
            logger.info(f"Downloaded {bucket}/{object_path} to {file_path}")
        except S3Error as e:
            logger.error(f"Error downloading file: {e}")
            raise
    
    def get_object(
        self,
        bucket: str,
        object_path: str
    ) -> bytes:
        """
        Get object data from MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            
        Returns:
            Object data as bytes
        """
        try:
            response = self.client.client.get_object(bucket, object_path)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Error getting object: {e}")
            raise
    
    def delete_object(
        self,
        bucket: str,
        object_path: str
    ) -> None:
        """
        Delete an object from MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
        """
        try:
            self.client.client.remove_object(bucket, object_path)
            logger.info(f"Deleted {bucket}/{object_path}")
        except S3Error as e:
            logger.error(f"Error deleting object: {e}")
            raise
    
    def list_objects(
        self,
        bucket: str,
        prefix: Optional[str] = None,
        recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List objects in a bucket.
        
        Args:
            bucket: Bucket name
            prefix: Filter by prefix
            recursive: List recursively
            
        Returns:
            List of object metadata dictionaries
        """
        try:
            objects = self.client.client.list_objects(
                bucket,
                prefix=prefix,
                recursive=recursive
            )
            
            result = []
            for obj in objects:
                result.append({
                    'object_name': obj.object_name,
                    'size': obj.size,
                    'etag': obj.etag,
                    'last_modified': obj.last_modified,
                    'content_type': obj.content_type
                })
            
            return result
        except S3Error as e:
            logger.error(f"Error listing objects: {e}")
            raise
    
    def object_exists(
        self,
        bucket: str,
        object_path: str
    ) -> bool:
        """
        Check if an object exists in MinIO.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            
        Returns:
            True if object exists, False otherwise
        """
        try:
            self.client.client.stat_object(bucket, object_path)
            return True
        except S3Error:
            return False
    
    def get_object_metadata(
        self,
        bucket: str,
        object_path: str
    ) -> Dict[str, Any]:
        """
        Get metadata for an object.
        
        Args:
            bucket: Bucket name
            object_path: Path to object within bucket
            
        Returns:
            Dictionary with object metadata
        """
        try:
            stat = self.client.client.stat_object(bucket, object_path)
            return {
                'size': stat.size,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'last_modified': stat.last_modified,
                'metadata': stat.metadata
            }
        except S3Error as e:
            logger.error(f"Error getting object metadata: {e}")
            raise
    
    def copy_object(
        self,
        source_bucket: str,
        source_object: str,
        dest_bucket: str,
        dest_object: str
    ) -> None:
        """
        Copy an object from one location to another.
        
        Args:
            source_bucket: Source bucket name
            source_object: Source object path
            dest_bucket: Destination bucket name
            dest_object: Destination object path
        """
        try:
            from minio.commonconfig import CopySource
            
            self.client.client.copy_object(
                dest_bucket,
                dest_object,
                CopySource(source_bucket, source_object)
            )
            logger.info(
                f"Copied {source_bucket}/{source_object} to "
                f"{dest_bucket}/{dest_object}"
            )
        except S3Error as e:
            logger.error(f"Error copying object: {e}")
            raise
    
    def generate_presigned_put_url(
        self, 
        bucket: str, 
        object_path: str, 
        expires_seconds: int = 3600
    ) -> str:
        """Generate presigned URL for uploading an object."""
        from datetime import timedelta
        try:
            # Use MinIOClient wrapper's ensure_bucket method
            self.client.ensure_bucket(bucket)
            
            url = self.client.client.presigned_put_object(
                bucket, 
                object_path, 
                expires=timedelta(seconds=expires_seconds)
            )
            
            # Replace internal MinIO endpoint with nginx proxy path
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            external_url = f'/minio{parsed.path}?{parsed.query}'
            
            return external_url
        except Exception as e:
            logger.error(f"Failed to generate presigned PUT URL for {bucket}/{object_path}: {e}")
            raise
    
    def validate_file_info(self, files_info: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate file upload information.
        
        Returns dict with validation result:
        - valid: bool
        - error: str (if not valid)
        - total_size: int (total bytes)
        """
        import re
        import os
        
        # Validate files array exists
        if not files_info:
            return {'valid': False, 'error': 'files array is required'}
        
        # Limit number of files
        if len(files_info) > 50:
            return {'valid': False, 'error': 'Maximum 50 files per upload'}
        
        # Validate each file
        max_file_size = 50 * 1024 * 1024 * 1024  # 50 GB
        total_size = 0
        
        for file_info in files_info:
            # Support both 'name'/'size' and 'filename'/'file_size' for flexibility
            name = file_info.get('name') or file_info.get('filename')
            size = file_info.get('size') or file_info.get('file_size')
            
            if not isinstance(file_info, dict) or not name or not size:
                return {'valid': False, 'error': 'Each file must have name/filename and size/file_size fields'}
            
            # Normalize to standard fields for consistency
            file_info['name'] = name
            file_info['size'] = size
            
            filename = file_info['name']
            file_size = file_info.get('size', 0)
            
            # Validate size
            if file_size <= 0 or file_size > max_file_size:
                return {'valid': False, 'error': f'File {filename}: size must be between 1 byte and 50GB'}
            
            total_size += file_size
            
            # Sanitize and validate filename
            filename = os.path.basename(filename)
            filename = filename.replace('\x00', '')
            
            if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
                return {'valid': False, 'error': f'Invalid filename: {file_info["name"]}. Use only alphanumeric, underscore, dot, and hyphen'}
            
            if len(filename) > 255:
                return {'valid': False, 'error': f'Filename too long: {filename}'}
            
            # Validate extension
            valid_extensions = ['.fastq', '.fq', '.fastq.gz', '.fq.gz', '.fasta', '.fa', '.fna']
            if not any(filename.endswith(ext) for ext in valid_extensions):
                return {'valid': False, 'error': f'Invalid file extension for {filename}. Allowed: {valid_extensions}'}
        
        # Check total size
        if total_size > 500 * 1024 * 1024 * 1024:  # 500 GB
            return {'valid': False, 'error': 'Total upload size exceeds 500GB limit'}
        
        return {'valid': True, 'total_size': total_size}
    
    def verify_object_exists(self, bucket: str, object_path: str) -> Dict[str, Any]:
        """
        Verify object exists in MinIO and get metadata.
        
        Returns:
            Dict with object metadata or raises exception if not found
        """
        try:
            stat = self.client.client.stat_object(bucket, object_path)
            return {
                'size': stat.size,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'last_modified': stat.last_modified
            }
        except Exception as e:
            logger.error(f"Object not found: {bucket}/{object_path}: {e}")
            raise ValueError(f"File not found in MinIO: {object_path}")

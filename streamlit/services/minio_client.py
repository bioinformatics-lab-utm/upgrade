# services/minio_client.py
import minio
from minio.error import S3Error
from datetime import datetime
from pathlib import Path
import logging
from config.settings import MINIO_CONFIG, FILE_VALIDATION

logger = logging.getLogger(__name__)

def get_minio_client():
    """Create MinIO client"""
    try:
        client = minio.Minio(
            endpoint=MINIO_CONFIG['endpoint'],
            access_key=MINIO_CONFIG['access_key'],
            secret_key=MINIO_CONFIG['secret_key'],
            secure=MINIO_CONFIG['secure']
        )
        return client
    except Exception as e:
        logger.error(f"MinIO connection error: {e}")
        return None

def validate_genomic_file(uploaded_file):
    """Validate uploaded genomic files"""
    errors = []
    
    # Check file extension
    file_name = uploaded_file.name.lower()
    if not any(file_name.endswith(ext) for ext in FILE_VALIDATION['allowed_extensions']):
        errors.append(f"Unsupported file type: {Path(uploaded_file.name).suffix}. Allowed: {', '.join(FILE_VALIDATION['allowed_extensions'])}")
    
    # Check file size
    if uploaded_file.size > FILE_VALIDATION['max_size_mb'] * 1024 * 1024:
        errors.append(f"File too large: {uploaded_file.size / (1024*1024):.1f}MB (max {FILE_VALIDATION['max_size_mb']}MB)")
    
    # Check minimum size
    if uploaded_file.size < FILE_VALIDATION['min_size_bytes']:
        errors.append("File too small (minimum 1KB)")
    
    return errors

def save_file_to_minio(uploaded_file, sample_id, bucket_name=None):
    """Save file to MinIO storage"""
    if bucket_name is None:
        bucket_name = MINIO_CONFIG['default_bucket']
        
    client = get_minio_client()
    if not client:
        return None, "MinIO client not available"
    
    try:
        # Create bucket if not exists
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"Created bucket: {bucket_name}")
        
        # Generate path in raw layer
        timestamp = datetime.now().strftime('%Y/%m/%d/%H')
        file_extension = Path(uploaded_file.name).suffix
        object_name = f"raw/{timestamp}/{sample_id}{file_extension}"
        
        # Save file
        uploaded_file.seek(0)
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=uploaded_file,
            length=uploaded_file.size,
            content_type='application/octet-stream'
        )
        
        logger.info(f"File uploaded to MinIO: {object_name}")
        return object_name, None
        
    except S3Error as e:
        error_msg = f"MinIO error: {e}"
        logger.error(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        logger.error(error_msg)
        return None, error_msg

def test_minio_connection():
    """Test MinIO connection"""
    client = get_minio_client()
    if not client:
        return False
    
    try:
        list(client.list_buckets())
        return True
    except Exception:
        return False
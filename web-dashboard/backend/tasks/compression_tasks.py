"""
Asynchronous file compression tasks for large uploads
"""
import os
import subprocess
import tempfile
import multiprocessing
import logging
from minio_helper import get_minio_client

logger = logging.getLogger(__name__)


def compress_file_async(bucket_name: str, object_path: str, sample_code: str, filename: str, original_size: int):
    """
    Asynchronously compress a file in MinIO
    
    Args:
        bucket_name: MinIO bucket (e.g., 'genomic-bronze')
        object_path: Path to uncompressed file in MinIO
        sample_code: Sample identifier
        filename: Original filename
        original_size: Size of uncompressed file in bytes
    
    Returns:
        Dict with compression results
    """
    from rq import get_current_job
    job = get_current_job()
    job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
    
    logger.info(f"[COMPRESSION] [{job_id}] Starting async compression for {filename} ({original_size / 1024 / 1024:.1f} MB)")
    
    try:
        import time
        start_time = time.time()
        
        minio_client = get_minio_client()
        
        # Create temp files for streaming
        tmp_in = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.fastq')
        tmp_out = tempfile.NamedTemporaryFile(mode='rb', delete=False, suffix='.fastq.gz')
        tmp_in_path = tmp_in.name
        tmp_out_path = tmp_out.name
        
        try:
            # Step 1: Stream download from MinIO
            download_start = time.time()
            logger.info(f"[COMPRESSION] [{job_id}] Downloading from MinIO...")
            response = minio_client.client.get_object(bucket_name, object_path)
            
            chunk_size = 64 * 1024 * 1024  # 64 MB chunks
            total_downloaded = 0
            
            for chunk in response.stream(chunk_size):
                tmp_in.write(chunk)
                total_downloaded += len(chunk)
            
            tmp_in.close()
            response.close()
            response.release_conn()
            
            download_time = time.time() - download_start
            download_speed = total_downloaded / download_time / 1024 / 1024
            logger.info(f"[COMPRESSION] [{job_id}] Downloaded {total_downloaded / 1024 / 1024:.1f} MB in {download_time:.1f}s ({download_speed:.1f} MB/s)")
            
            # Step 2: Compress with pigz
            compress_start = time.time()
            max_threads = multiprocessing.cpu_count()
            logger.info(f"[COMPRESSION] [{job_id}] Compressing with pigz -p {max_threads}...")
            
            result = subprocess.run(
                ['pigz', '-p', str(max_threads), '-6', '-c', tmp_in_path],
                stdout=open(tmp_out_path, 'wb'),
                stderr=subprocess.PIPE,
                check=True
            )
            
            compress_time = time.time() - compress_start
            compressed_size = os.path.getsize(tmp_out_path)
            compression_ratio = (1 - compressed_size / total_downloaded) * 100
            compress_speed = total_downloaded / compress_time / 1024 / 1024
            logger.info(f"[COMPRESSION] [{job_id}] Compressed: {total_downloaded / 1024 / 1024:.1f} MB → {compressed_size / 1024 / 1024:.1f} MB in {compress_time:.1f}s ({compress_speed:.1f} MB/s, {compression_ratio:.1f}% reduction)")
            
            # Step 3: Upload compressed file
            upload_start = time.time()
            compressed_filename = filename + '.gz'
            compressed_path = f"{sample_code}/raw/{compressed_filename}"
            logger.info(f"[COMPRESSION] [{job_id}] Uploading compressed to MinIO: {compressed_size / 1024 / 1024:.1f} MB...")
            
            with open(tmp_out_path, 'rb') as compressed_file:
                minio_client.client.put_object(
                    bucket_name,
                    compressed_path,
                    compressed_file,
                    compressed_size,
                    content_type='application/gzip'
                )
            
            upload_time = time.time() - upload_start
            upload_speed = compressed_size / upload_time / 1024 / 1024
            logger.info(f"[COMPRESSION] [{job_id}] Uploaded {compressed_size / 1024 / 1024:.1f} MB in {upload_time:.1f}s ({upload_speed:.1f} MB/s)")
            
            # Step 4: Delete uncompressed file
            delete_start = time.time()
            minio_client.client.remove_object(bucket_name, object_path)
            delete_time = time.time() - delete_start
            logger.info(f"[COMPRESSION] [{job_id}] Deleted original (took {delete_time:.3f}s)")
            
            total_time = time.time() - start_time
            logger.info(f"[COMPRESSION] [{job_id}] ✓ Compression complete: {total_time:.1f}s total")
            
            return {
                'success': True,
                'compressed_path': compressed_path,
                'compressed_filename': compressed_filename,
                'original_size': total_downloaded,
                'compressed_size': compressed_size,
                'compression_ratio': compression_ratio,
                'times': {
                    'download': download_time,
                    'compress': compress_time,
                    'upload': upload_time,
                    'delete': delete_time,
                    'total': total_time
                }
            }
            
        finally:
            # Cleanup temp files
            for tmp_path in [tmp_in_path, tmp_out_path]:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
    
    except Exception as e:
        logger.error(f"[COMPRESSION] [{job_id}] Compression failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }

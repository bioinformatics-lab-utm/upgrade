"""
Retention Policy Enforcement Tasks
Automatically clean up expired files from Silver layer based on retention policies
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import asyncio

from database import DatabasePool
from minio_helper import get_minio_client
from config import config

logger = logging.getLogger(__name__)


async def enforce_retention_policy() -> Dict:
    """
    Apply retention policies to MinIO objects
    
    This function identifies and removes expired objects from buckets
    based on their defined retention_policy:
    - 'archive_1year': Delete objects older than 1 year
    - 'archive_6months': Delete objects older than 6 months
    - 'permanent': Never delete
    
    Returns:
        dict: Summary of enforcement actions
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("RETENTION POLICY ENFORCEMENT - Starting")
    logger.info("=" * 60)
    
    result = {
        'start_time': start_time.isoformat(),
        'buckets_processed': 0,
        'objects_deleted': 0,
        'bytes_freed': 0,
        'errors': []
    }
    
    try:
        pool = DatabasePool.get_pool()
        minio_client = get_minio_client()
        
        async with pool.acquire() as conn:
            # Get all buckets with retention policies
            buckets = await conn.fetch("""
                SELECT 
                    bucket_id,
                    bucket_name,
                    retention_policy,
                    layer_type
                FROM minio_buckets
                WHERE retention_policy IS NOT NULL
                  AND retention_policy != 'permanent'
                ORDER BY bucket_name
            """)
            
            logger.info(f"Found {len(buckets)} buckets with non-permanent retention policies")
            
            for bucket in buckets:
                bucket_name = bucket['bucket_name']
                retention_policy = bucket['retention_policy']
                bucket_id = bucket['bucket_id']
                
                logger.info(f"Processing bucket: {bucket_name} (policy: {retention_policy})")
                
                # Determine retention period
                if retention_policy == 'archive_1year':
                    retention_days = 365
                elif retention_policy == 'archive_6months':
                    retention_days = 180
                elif retention_policy == 'archive_3months':
                    retention_days = 90
                else:
                    logger.warning(f"Unknown retention policy '{retention_policy}', skipping")
                    continue
                
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                logger.info(f"  Cutoff date: {cutoff_date.strftime('%Y-%m-%d')} ({retention_days} days)")
                
                # Find expired objects
                expired_objects = await conn.fetch("""
                    SELECT 
                        object_id,
                        object_key,
                        object_name,
                        object_size_bytes,
                        created_at
                    FROM minio_objects
                    WHERE bucket_id = $1
                      AND created_at < $2
                    ORDER BY created_at ASC
                """, bucket_id, cutoff_date)
                
                if not expired_objects:
                    logger.info(f"  No expired objects found")
                    result['buckets_processed'] += 1
                    continue
                
                logger.info(f"  Found {len(expired_objects)} expired objects")
                logger.info(f"  Total size: {sum(obj['object_size_bytes'] for obj in expired_objects) / (1024**3):.2f} GB")
                
                # Delete objects from MinIO and database
                deleted_count = 0
                deleted_bytes = 0
                
                for obj in expired_objects:
                    object_key = obj['object_key']
                    object_id = obj['object_id']
                    object_size = obj['object_size_bytes']
                    
                    try:
                        # Delete from MinIO
                        minio_client.client.remove_object(bucket_name, object_key)
                        
                        # Delete from database (cascade will remove lineage records)
                        await conn.execute("""
                            DELETE FROM minio_objects WHERE object_id = $1
                        """, object_id)
                        
                        deleted_count += 1
                        deleted_bytes += object_size
                        
                        if deleted_count % 100 == 0:
                            logger.info(f"  Progress: {deleted_count}/{len(expired_objects)} objects deleted")
                        
                    except Exception as e:
                        error_msg = f"Failed to delete {object_key}: {str(e)}"
                        logger.error(f"  {error_msg}")
                        result['errors'].append(error_msg)
                
                logger.info(f"  ✓ Deleted {deleted_count} objects, freed {deleted_bytes / (1024**3):.2f} GB")
                
                result['buckets_processed'] += 1
                result['objects_deleted'] += deleted_count
                result['bytes_freed'] += deleted_bytes
        
        # Final summary
        duration = (datetime.now() - start_time).total_seconds()
        result['end_time'] = datetime.now().isoformat()
        result['duration_seconds'] = duration
        
        logger.info("=" * 60)
        logger.info("RETENTION POLICY ENFORCEMENT - Summary")
        logger.info(f"  Buckets processed: {result['buckets_processed']}")
        logger.info(f"  Objects deleted: {result['objects_deleted']}")
        logger.info(f"  Storage freed: {result['bytes_freed'] / (1024**3):.2f} GB")
        logger.info(f"  Duration: {duration:.1f} seconds")
        logger.info(f"  Errors: {len(result['errors'])}")
        logger.info("=" * 60)
        
        return result
        
    except Exception as e:
        logger.error(f"Retention policy enforcement failed: {e}", exc_info=True)
        result['error'] = str(e)
        return result


def enforce_retention_policy_sync():
    """Synchronous wrapper for RQ scheduler"""
    return asyncio.run(enforce_retention_policy())


async def preview_retention_policy() -> Dict:
    """
    Preview what would be deleted without actually deleting
    Useful for testing and reporting
    
    Returns:
        dict: Preview of objects that would be deleted
    """
    logger.info("RETENTION POLICY PREVIEW (Dry Run)")
    
    preview = {
        'timestamp': datetime.now().isoformat(),
        'buckets': []
    }
    
    try:
        pool = DatabasePool.get_pool()
        
        async with pool.acquire() as conn:
            buckets = await conn.fetch("""
                SELECT 
                    bucket_id,
                    bucket_name,
                    retention_policy,
                    layer_type
                FROM minio_buckets
                WHERE retention_policy IS NOT NULL
                  AND retention_policy != 'permanent'
            """)
            
            for bucket in buckets:
                bucket_name = bucket['bucket_name']
                retention_policy = bucket['retention_policy']
                bucket_id = bucket['bucket_id']
                
                # Determine retention period
                if retention_policy == 'archive_1year':
                    retention_days = 365
                elif retention_policy == 'archive_6months':
                    retention_days = 180
                elif retention_policy == 'archive_3months':
                    retention_days = 90
                else:
                    continue
                
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                
                # Find expired objects
                expired_objects = await conn.fetch("""
                    SELECT 
                        COUNT(*) as object_count,
                        SUM(object_size_bytes) as total_bytes,
                        MIN(created_at) as oldest_file,
                        MAX(created_at) as newest_expired_file
                    FROM minio_objects
                    WHERE bucket_id = $1
                      AND created_at < $2
                """, bucket_id, cutoff_date)
                
                if expired_objects and expired_objects[0]['object_count'] > 0:
                    obj = expired_objects[0]
                    bucket_preview = {
                        'bucket_name': bucket_name,
                        'retention_policy': retention_policy,
                        'retention_days': retention_days,
                        'cutoff_date': cutoff_date.isoformat(),
                        'expired_objects': obj['object_count'],
                        'storage_to_free_gb': obj['total_bytes'] / (1024**3) if obj['total_bytes'] else 0,
                        'oldest_file': obj['oldest_file'].isoformat() if obj['oldest_file'] else None,
                        'newest_expired_file': obj['newest_expired_file'].isoformat() if obj['newest_expired_file'] else None
                    }
                    preview['buckets'].append(bucket_preview)
                    
                    logger.info(f"Bucket: {bucket_name}")
                    logger.info(f"  Would delete: {obj['object_count']} objects")
                    logger.info(f"  Would free: {bucket_preview['storage_to_free_gb']:.2f} GB")
        
        preview['total_objects'] = sum(b['expired_objects'] for b in preview['buckets'])
        preview['total_gb'] = sum(b['storage_to_free_gb'] for b in preview['buckets'])
        
        logger.info(f"TOTAL: {preview['total_objects']} objects, {preview['total_gb']:.2f} GB")
        
        return preview
        
    except Exception as e:
        logger.error(f"Preview failed: {e}", exc_info=True)
        preview['error'] = str(e)
        return preview


# ==================== RQ TASK REGISTRATION ====================

def schedule_retention_enforcement():
    """
    Schedule retention policy enforcement to run daily at 2 AM
    
    Usage:
        from tasks.retention_tasks import schedule_retention_enforcement
        schedule_retention_enforcement()
    """
    from redis import Redis
    from rq_scheduler import Scheduler
    
    redis_conn = Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD,
        decode_responses=True
    )
    
    scheduler = Scheduler(connection=redis_conn)
    
    # Schedule daily at 2 AM
    scheduler.cron(
        '0 2 * * *',  # At 02:00 every day
        func=enforce_retention_policy_sync,
        queue_name='maintenance',
        timeout='1h'
    )
    
    logger.info("✓ Retention policy enforcement scheduled (daily at 2 AM)")


if __name__ == '__main__':
    # Test run
    import asyncio
    
    logger.info("Running retention policy preview...")
    preview = asyncio.run(preview_retention_policy())

    logger.info("Preview Results:")
    logger.info(f"Total objects to delete: {preview.get('total_objects', 0)}")
    logger.info(f"Total storage to free: {preview.get('total_gb', 0):.2f} GB")
    
    # Uncomment to actually run enforcement
    # print("\nRunning enforcement...")
    # result = asyncio.run(enforce_retention_policy())

#!/usr/bin/env python3
"""
Orphan Data Detection Script

Detects orphaned data:
1. MinIO objects without database records
2. Database records without corresponding MinIO objects
3. Results directories without pipeline records
4. Pipeline records without results

Run regularly to maintain data integrity.

Usage:
    python scripts/detect_orphan_data.py [--dry-run] [--fix]
    python scripts/detect_orphan_data.py --host [--summary]  # From host machine
"""
import asyncio
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import logging

# Parse args early to know if we're running from host
_pre_parser = argparse.ArgumentParser(add_help=False)
_pre_parser.add_argument('--host', action='store_true', help='Run from host (uses localhost:5433)')
_pre_args, _ = _pre_parser.parse_known_args()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'web-dashboard' / 'backend'))

# Load environment - .env file takes priority for credentials
env_file = Path(__file__).parent.parent / '.env'
CREDENTIAL_VARS = {'POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'MINIO_ROOT_PASSWORD', 'MINIO_ROOT_USER'}
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # For credentials, always use .env file value (shell may strip trailing = etc)
                if key in CREDENTIAL_VARS or key not in os.environ:
                    os.environ[key] = value

# If running from host, override network settings
if _pre_args.host:
    os.environ['POSTGRES_HOST'] = 'localhost'
    os.environ['POSTGRES_PORT'] = '5433'
    os.environ['MINIO_ENDPOINT'] = 'localhost:9000'

from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Build database URL with proper encoding for external scripts
def get_database_url():
    """Build database URL with URL-encoded password"""
    from urllib.parse import quote_plus
    user = os.environ.get('POSTGRES_USER', 'upgrade')
    password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
    host = os.environ.get('POSTGRES_HOST', 'localhost')
    port = os.environ.get('POSTGRES_PORT', '5432')
    db = os.environ.get('POSTGRES_DB', 'upgrade_db')
    # URL-encode password to handle special characters
    encoded_password = quote_plus(password)
    return f"postgresql://{user}:{encoded_password}@{host}:{port}/{db}"

DATABASE_URL = get_database_url()


def get_minio_client():
    """Get MinIO client"""
    from minio import Minio
    endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
    if _pre_args.host:
        endpoint = 'localhost:9000'
    return Minio(
        endpoint,
        access_key=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        secret_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        secure=False
    )


async def detect_orphan_minio_objects(conn, minio_client, buckets: list) -> dict:
    """
    Detect MinIO objects not tracked in database.
    """
    logger.info("\n🔍 Checking for orphan MinIO objects...")
    
    # Get all tracked objects from database (join with minio_buckets for bucket_name)
    db_objects = await conn.fetch("""
        SELECT b.bucket_name, o.object_key 
        FROM minio_objects o
        JOIN minio_buckets b ON o.bucket_id = b.bucket_id
    """)
    tracked = {(row['bucket_name'], row['object_key']) for row in db_objects}
    logger.info(f"  Database tracks {len(tracked)} objects")
    
    orphans = []
    total_size = 0
    
    for bucket in buckets:
        try:
            objects = minio_client.list_objects(bucket, recursive=True)
            for obj in objects:
                key = (bucket, obj.object_name)
                if key not in tracked:
                    orphans.append({
                        'bucket': bucket,
                        'key': obj.object_name,
                        'size': obj.size,
                        'modified': obj.last_modified
                    })
                    total_size += obj.size
        except Exception as e:
            logger.warning(f"  Could not scan bucket {bucket}: {e}")
    
    if orphans:
        logger.warning(f"  ⚠️  Found {len(orphans)} orphan MinIO objects ({total_size / 1024 / 1024:.1f} MB)")
        for o in orphans[:10]:  # Show first 10
            logger.warning(f"    - {o['bucket']}/{o['key']} ({o['size'] / 1024:.1f} KB)")
        if len(orphans) > 10:
            logger.warning(f"    ... and {len(orphans) - 10} more")
    else:
        logger.info("  ✅ No orphan MinIO objects found")
    
    return {'orphans': orphans, 'total_size': total_size}


async def detect_missing_minio_objects(conn, minio_client, buckets: list) -> dict:
    """
    Detect database records pointing to non-existent MinIO objects.
    """
    logger.info("\n🔍 Checking for missing MinIO objects...")
    
    missing = []
    
    # Get all tracked objects from database (join with minio_buckets for bucket_name)
    db_objects = await conn.fetch("""
        SELECT o.object_id, b.bucket_name, o.object_key, o.object_size_bytes, o.created_at 
        FROM minio_objects o
        JOIN minio_buckets b ON o.bucket_id = b.bucket_id
    """)
    
    for row in db_objects:
        bucket = row['bucket_name']
        key = row['object_key']
        
        try:
            minio_client.stat_object(bucket, key)
        except Exception:
            missing.append({
                'object_id': row['object_id'],
                'bucket': bucket,
                'key': key,
                'size': row['object_size_bytes'],
                'created_at': row['created_at']
            })
    
    if missing:
        logger.warning(f"  ⚠️  Found {len(missing)} database records pointing to missing files")
        for m in missing[:10]:
            logger.warning(f"    - ID {m['object_id']}: {m['bucket']}/{m['key']}")
        if len(missing) > 10:
            logger.warning(f"    ... and {len(missing) - 10} more")
    else:
        logger.info("  ✅ All database records have corresponding MinIO objects")
    
    return {'missing': missing}


async def detect_orphan_results_dirs(conn, results_dir: Path) -> dict:
    """
    Detect results directories without corresponding pipeline records.
    """
    logger.info("\n🔍 Checking for orphan results directories...")
    
    if not results_dir.exists():
        logger.warning(f"  Results directory does not exist: {results_dir}")
        return {'orphans': []}
    
    # Get all sample names with completed pipelines
    db_samples = await conn.fetch("""
        SELECT DISTINCT sample_name FROM pipeline_runs
        WHERE results_path IS NOT NULL
    """)
    known_samples = {row['sample_name'] for row in db_samples if row['sample_name']}
    
    orphans = []
    total_size = 0
    
    for subdir in results_dir.iterdir():
        if subdir.is_dir() and not subdir.name.startswith('.'):
            if subdir.name not in known_samples:
                # Calculate directory size
                dir_size = sum(f.stat().st_size for f in subdir.rglob('*') if f.is_file())
                orphans.append({
                    'path': str(subdir),
                    'name': subdir.name,
                    'size': dir_size,
                    'modified': datetime.fromtimestamp(subdir.stat().st_mtime)
                })
                total_size += dir_size
    
    if orphans:
        logger.warning(f"  ⚠️  Found {len(orphans)} orphan results directories ({total_size / 1024 / 1024:.1f} MB)")
        for o in orphans[:10]:
            logger.warning(f"    - {o['name']} ({o['size'] / 1024 / 1024:.1f} MB)")
        if len(orphans) > 10:
            logger.warning(f"    ... and {len(orphans) - 10} more")
    else:
        logger.info("  ✅ No orphan results directories found")
    
    return {'orphans': orphans, 'total_size': total_size}


async def detect_pipelines_without_results(conn, results_dir: Path) -> dict:
    """
    Detect completed pipelines without results directories.
    """
    logger.info("\n🔍 Checking for pipelines missing results...")
    
    # Get completed pipelines
    completed = await conn.fetch("""
        SELECT pipeline_id, sample_name, results_path, completed_at
        FROM pipeline_runs
        WHERE status = 'completed' AND results_path IS NOT NULL
    """)
    
    missing = []
    for row in completed:
        results_path = Path(row['results_path'])
        if not results_path.exists():
            missing.append({
                'pipeline_id': row['pipeline_id'],
                'sample_name': row['sample_name'],
                'results_path': row['results_path'],
                'completed_at': row['completed_at']
            })
    
    if missing:
        logger.warning(f"  ⚠️  Found {len(missing)} completed pipelines with missing results")
        for m in missing[:10]:
            logger.warning(f"    - Pipeline {m['pipeline_id']} ({m['sample_name']}): {m['results_path']}")
        if len(missing) > 10:
            logger.warning(f"    ... and {len(missing) - 10} more")
    else:
        logger.info("  ✅ All completed pipelines have results directories")
    
    return {'missing': missing}


async def run_detection(dry_run: bool = True, fix: bool = False):
    """Run all orphan detection checks"""
    import asyncpg
    
    logger.info("=" * 60)
    logger.info("ORPHAN DATA DETECTION")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Auto-fix: {fix}")
    logger.info("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    minio_client = get_minio_client()
    results_dir = Path(config.RESULTS_DIR)
    
    buckets = ['genomic-bronze', 'genomic-silver', 'genomic-gold']
    
    try:
        # Run all detections
        orphan_minio = await detect_orphan_minio_objects(conn, minio_client, buckets)
        missing_minio = await detect_missing_minio_objects(conn, minio_client, buckets)
        orphan_results = await detect_orphan_results_dirs(conn, results_dir)
        missing_results = await detect_pipelines_without_results(conn, results_dir)
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        
        issues = []
        if orphan_minio['orphans']:
            issues.append(f"{len(orphan_minio['orphans'])} orphan MinIO objects")
        if missing_minio['missing']:
            issues.append(f"{len(missing_minio['missing'])} missing MinIO objects")
        if orphan_results['orphans']:
            issues.append(f"{len(orphan_results['orphans'])} orphan results dirs")
        if missing_results['missing']:
            issues.append(f"{len(missing_results['missing'])} pipelines missing results")
        
        if issues:
            logger.warning(f"⚠️  Issues found: {', '.join(issues)}")
            
            if fix and not dry_run:
                logger.info("\n🔧 Auto-fix enabled - cleaning up...")
                
                # Fix: Remove DB records for missing MinIO objects
                for m in missing_minio['missing']:
                    await conn.execute(
                        "DELETE FROM minio_objects WHERE object_id = $1",
                        m['object_id']
                    )
                    logger.info(f"  Removed DB record for missing object ID {m['object_id']}")
                
                # Note: We don't auto-delete orphan MinIO objects or results dirs
                # as they may contain valuable data
                if orphan_minio['orphans']:
                    logger.warning("  ⚠️  Orphan MinIO objects require manual review")
                if orphan_results['orphans']:
                    logger.warning("  ⚠️  Orphan results directories require manual review")
                
                logger.info("  ✅ Auto-fix completed")
        else:
            logger.info("✅ No data integrity issues found")
        
        return {
            'orphan_minio': orphan_minio,
            'missing_minio': missing_minio,
            'orphan_results': orphan_results,
            'missing_results': missing_results,
            'has_issues': bool(issues)
        }
        
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Detect orphan data")
    parser.add_argument('--host', action='store_true',
                        help='Run from host machine (uses localhost:5433 for postgres)')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Preview without making changes (default)')
    parser.add_argument('--fix', action='store_true',
                        help='Auto-fix safe issues (remove DB records for missing objects)')
    
    args = parser.parse_args()
    
    # Default to dry-run unless explicitly fixing
    dry_run = not args.fix or args.dry_run
    
    asyncio.run(run_detection(dry_run=dry_run, fix=args.fix))


if __name__ == "__main__":
    main()

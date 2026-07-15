#!/usr/bin/env python3
"""
Stuck Pipeline Recovery Script

Detects and recovers pipelines stuck in queued/running state.
Run periodically via cron to ensure no pipelines are left hanging.

Usage:
    python scripts/recover_stuck_pipelines.py [--dry-run] [--queued-timeout 60] [--running-timeout 24]
    python scripts/recover_stuck_pipelines.py --host [--summary-only]   # From host machine
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


async def check_rq_job_status(job_id: str) -> dict:
    """Check if RQ job is actually running or orphaned"""
    try:
        from rq import Queue
        from rq.job import Job
        import redis
        
        redis_conn = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD
        )
        
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        
        return {
            'exists': True,
            'status': status.decode() if isinstance(status, bytes) else status,
            'started_at': job.started_at,
            'ended_at': job.ended_at
        }
    except Exception as e:
        return {
            'exists': False,
            'error': str(e)
        }


async def recover_stuck_pipelines(
    dry_run: bool = True,
    queued_timeout: int = 60,
    running_timeout: int = 24
):
    """
    Find and recover stuck pipelines.
    
    Args:
        dry_run: If True, only report without making changes
        queued_timeout: Minutes after which queued is stuck
        running_timeout: Hours after which running is stuck
    """
    import asyncpg
    
    logger.info("=" * 60)
    logger.info("STUCK PIPELINE RECOVERY")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Queued timeout: {queued_timeout} minutes")
    logger.info(f"Running timeout: {running_timeout} hours")
    logger.info("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Find stuck pipelines
        stuck_query = """
            SELECT 
                pipeline_id, sample_id, sample_name, status, 
                job_id, created_at, started_at
            FROM pipeline_runs
            WHERE 
                (status = 'queued' AND created_at < NOW() - INTERVAL '%s minutes')
                OR 
                (status = 'running' AND started_at < NOW() - INTERVAL '%s hours')
                OR
                (status = 'pending' AND created_at < NOW() - INTERVAL '%s minutes')
            ORDER BY created_at ASC
        """ % (queued_timeout, running_timeout, queued_timeout)
        
        stuck = await conn.fetch(stuck_query)
        
        if not stuck:
            logger.info("✅ No stuck pipelines found")
            return
        
        logger.info(f"⚠️  Found {len(stuck)} stuck pipelines")
        
        recovered = 0
        for row in stuck:
            pipeline_id = row['pipeline_id']
            status = row['status']
            job_id = row['job_id']
            sample_name = row['sample_name'] or f"sample_{row['sample_id']}"
            
            logger.info(f"\n--- Pipeline {pipeline_id} ({sample_name}) ---")
            logger.info(f"  Status: {status}")
            logger.info(f"  Created: {row['created_at']}")
            logger.info(f"  Started: {row['started_at']}")
            logger.info(f"  Job ID: {job_id}")
            
            # Check RQ job status if we have a job_id
            rq_status = None
            if job_id:
                rq_status = await check_rq_job_status(job_id)
                logger.info(f"  RQ Status: {rq_status}")
            
            # Determine error message
            if status == 'queued':
                error_msg = f"Stuck in queue for over {queued_timeout} minutes - marked as failed by recovery"
            elif status == 'pending':
                error_msg = f"Stuck in pending state for over {queued_timeout} minutes - marked as failed by recovery"
            else:
                error_msg = f"Execution exceeded {running_timeout} hour timeout - marked as failed by recovery"
            
            if rq_status and not rq_status.get('exists'):
                error_msg += f" (RQ job orphaned: {rq_status.get('error', 'not found')})"
            
            if dry_run:
                logger.info(f"  [DRY-RUN] Would mark as failed: {error_msg}")
            else:
                # Mark as failed
                update_query = """
                    UPDATE pipeline_runs
                    SET status = 'failed', 
                        completed_at = NOW(),
                        error_message = $1
                    WHERE pipeline_id = $2
                """
                await conn.execute(update_query, error_msg, pipeline_id)
                logger.info(f"  ✅ Marked as failed")
                recovered += 1
        
        logger.info("\n" + "=" * 60)
        if dry_run:
            logger.info(f"[DRY-RUN] Would recover {len(stuck)} pipelines")
        else:
            logger.info(f"✅ Recovered {recovered} stuck pipelines")
        
    finally:
        await conn.close()


async def get_pipeline_health_summary():
    """Get a summary of pipeline health status"""
    import asyncpg
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        summary = await conn.fetch("""
            SELECT 
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM pipeline_runs
            GROUP BY status
            ORDER BY count DESC
        """)
        
        logger.info("\n📊 PIPELINE HEALTH SUMMARY")
        logger.info("-" * 50)
        for row in summary:
            logger.info(f"  {row['status']:12} : {row['count']:5} pipelines")
            if row['status'] in ('queued', 'running', 'pending'):
                logger.info(f"               oldest: {row['oldest']}")
        
        # Check for any active pipelines
        active = await conn.fetchval("""
            SELECT COUNT(*) FROM pipeline_runs
            WHERE status IN ('queued', 'running', 'pending')
        """)
        
        if active > 0:
            logger.info(f"\n⚠️  {active} pipelines currently active")
        else:
            logger.info("\n✅ No active pipelines")
            
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Recover stuck pipelines")
    parser.add_argument('--host', action='store_true', 
                        help='Run from host machine (uses localhost:5433 for postgres)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--queued-timeout', type=int, default=60, 
                        help='Minutes after which queued is stuck (default: 60)')
    parser.add_argument('--running-timeout', type=int, default=24,
                        help='Hours after which running is stuck (default: 24)')
    parser.add_argument('--summary-only', action='store_true',
                        help='Only show health summary')
    
    args = parser.parse_args()
    
    async def run():
        await get_pipeline_health_summary()
        
        if not args.summary_only:
            await recover_stuck_pipelines(
                dry_run=args.dry_run,
                queued_timeout=args.queued_timeout,
                running_timeout=args.running_timeout
            )
    
    asyncio.run(run())


if __name__ == "__main__":
    main()

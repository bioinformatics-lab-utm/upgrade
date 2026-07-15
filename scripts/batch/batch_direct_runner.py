#!/usr/bin/env python3
"""
Direct Batch Pipeline Runner
Bypasses API and directly queues pipeline jobs using internal services
More reliable for large batch processing
"""

import os
import sys
import asyncio
import asyncpg
from pathlib import Path
from datetime import datetime
import logging

# Add backend to path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent.parent / 'web-dashboard' / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/batch_direct.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration — use relative paths from project root
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = Path(os.getenv('DATA_DIR', str(PROJECT_ROOT / 'data')))
RESULTS_BASE = Path(os.getenv('RESULTS_DIR', str(PROJECT_ROOT / 'results')))
WORK_BASE = Path(os.getenv('NXF_WORK', '/data/nextflow-work'))

# Database configuration — no hardcoded credentials
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5433')),
    'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
    'user': os.getenv('POSTGRES_USER', 'upgrade'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

if not DB_CONFIG['password']:
    logger.error("POSTGRES_PASSWORD environment variable is required")
    sys.exit(1)

# Default pipeline parameters
DEFAULT_PARAMS = {
    'flye_genome_size': '50m',
    'flye_meta': True,
    'threads': 60,
    'flye_mode': '--nano-raw',
    'run_medaka': True,
    'contig_min_length': 1500,
    'metabat2_min_contig': 1500,
    'concoct_min_contig': 1000,
    'skip_bin_quality_filter': False,
    'bin_filter_completeness': 20,
    'bin_filter_contamination': 20
}


class DirectBatchRunner:
    """Direct batch runner using internal pipeline services"""
    
    def __init__(self):
        self.db_pool = None
        
    async def init_db(self):
        """Initialize database connection"""
        try:
            self.db_pool = await asyncpg.create_pool(**DB_CONFIG)
            logger.info("✓ Database connection established")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise
    
    async def close_db(self):
        """Close database connection"""
        if self.db_pool:
            await self.db_pool.close()
    
    def find_fastq_files(self):
        """Find all FASTQ files in data directory"""
        logger.info(f"Scanning {DATA_DIR} for FASTQ files...")
        
        fastq_files = []
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                if file.endswith('.fastq') or file.endswith('.fastq.gz'):
                    full_path = Path(root) / file
                    
                    # Extract sample code from directory structure
                    rel_path = full_path.relative_to(DATA_DIR)
                    parts = rel_path.parts
                    
                    if len(parts) >= 1:
                        sample_code = parts[0]
                        
                        # Skip if not an SRR/ERR/DRR accession format
                        if not (sample_code.startswith('SRR') or 
                               sample_code.startswith('ERR') or 
                               sample_code.startswith('DRR')):
                            continue
                        
                        fastq_files.append({
                            'path': str(full_path),
                            'sample_code': sample_code,
                            'filename': file,
                            'size_mb': full_path.stat().st_size / 1024 / 1024
                        })
        
        # Sort by sample code
        fastq_files.sort(key=lambda x: x['sample_code'])
        
        logger.info(f"✓ Found {len(fastq_files)} FASTQ files")
        return fastq_files
    
    async def ensure_sample_exists(self, sample_code, fastq_path):
        """Ensure sample record exists, create if needed"""
        async with self.db_pool.acquire() as conn:
            # Check if exists
            sample_id = await conn.fetchval(
                "SELECT sample_id FROM samples WHERE sample_code = $1",
                sample_code
            )
            
            if sample_id:
                return sample_id
            
            # Create new sample
            try:
                sample_id = await conn.fetchval("""
                    INSERT INTO samples (
                        sample_code, 
                        sample_type, 
                        collection_date,
                        notes,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING sample_id
                """, 
                    sample_code,
                    'metagenomic',
                    datetime.now().date(),
                    f'Batch imported from {fastq_path}',
                    datetime.now()
                )
                logger.info(f"  ✓ Created sample: {sample_code} (ID: {sample_id})")
                return sample_id
            except Exception as e:
                logger.error(f"  ✗ Failed to create sample {sample_code}: {e}")
                return None
    
    async def pipeline_exists(self, sample_code):
        """Check if active pipeline already exists"""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT pr.pipeline_id 
                FROM pipeline_runs pr
                JOIN samples s ON pr.sample_id = s.sample_id
                WHERE s.sample_code = $1
                AND pr.status IN ('queued', 'running', 'completed')
            """, sample_code)
            return result
    
    async def create_pipeline_run(self, sample_id, sample_code, params):
        """Create pipeline run record"""
        async with self.db_pool.acquire() as conn:
            try:
                # Prepare paths
                results_path = f"/results/{sample_code}"
                log_path = f"{results_path}/nextflow.log"
                work_path = f"/tmp/nextflow/work/{sample_code}"
                
                # Create directories
                Path(results_path).mkdir(parents=True, exist_ok=True)
                Path(work_path).mkdir(parents=True, exist_ok=True)
                
                # Create job ID
                job_id = f"batch_{sample_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                # Insert pipeline run
                pipeline_id = await conn.fetchval("""
                    INSERT INTO pipeline_runs (
                        sample_id,
                        sample_name,
                        pipeline_name,
                        parameters,
                        status,
                        job_id,
                        results_path,
                        log_path,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING pipeline_id
                """,
                    sample_id,
                    sample_code,
                    'nextflow_pipeline',
                    params,  # JSONB
                    'queued',
                    job_id,
                    results_path,
                    log_path,
                    datetime.now()
                )
                
                logger.info(f"  ✓ Created pipeline run: ID={pipeline_id}, Job={job_id}")
                return pipeline_id, job_id
                
            except Exception as e:
                logger.error(f"  ✗ Failed to create pipeline run: {e}")
                return None, None
    
    async def queue_pipeline_job(self, pipeline_id, sample_code, fastq_path):
        """Queue pipeline execution job using RQ"""
        try:
            from redis import Redis
            from rq import Queue
            
            # Connect to Redis
            redis_conn = Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=0
            )
            
            # Get pipeline queue
            queue = Queue('pipeline-queue', connection=redis_conn)
            
            # Queue job (using tasks.pipeline_tasks:run_pipeline_task)
            job = queue.enqueue(
                'tasks.pipeline_tasks.run_pipeline_task',
                pipeline_id,
                sample_code,
                str(fastq_path),
                DEFAULT_PARAMS,
                job_timeout='24h',
                result_ttl=3600
            )
            
            logger.info(f"  ✓ Queued RQ job: {job.id}")
            return job.id
            
        except Exception as e:
            logger.error(f"  ✗ Failed to queue job: {e}")
            return None
    
    async def submit_sample(self, sample_code, fastq_path):
        """Submit single sample for processing"""
        
        # Check if pipeline already exists
        existing = await self.pipeline_exists(sample_code)
        if existing:
            logger.warning(f"  ⊘ Pipeline already exists (ID: {existing}), skipping")
            return {'success': False, 'reason': 'exists'}
        
        # Ensure sample exists
        sample_id = await self.ensure_sample_exists(sample_code, fastq_path)
        if not sample_id:
            return {'success': False, 'reason': 'sample_failed'}
        
        # Create pipeline run
        pipeline_id, job_id = await self.create_pipeline_run(
            sample_id, sample_code, DEFAULT_PARAMS
        )
        if not pipeline_id:
            return {'success': False, 'reason': 'pipeline_failed'}
        
        # Queue job
        rq_job_id = await self.queue_pipeline_job(pipeline_id, sample_code, fastq_path)
        if not rq_job_id:
            return {'success': False, 'reason': 'queue_failed'}
        
        return {
            'success': True,
            'pipeline_id': pipeline_id,
            'job_id': job_id,
            'rq_job_id': rq_job_id
        }
    
    async def process_batch(self, limit=None, skip_existing=True):
        """Process all FASTQ files"""
        
        logger.info("=" * 80)
        logger.info("  🚀 DIRECT BATCH PIPELINE RUNNER")
        logger.info("=" * 80)
        
        # Initialize
        await self.init_db()
        
        # Find files
        fastq_files = self.find_fastq_files()
        
        if not fastq_files:
            logger.warning("No FASTQ files found!")
            await self.close_db()
            return
        
        if limit:
            fastq_files = fastq_files[:limit]
        
        logger.info(f"\n📊 Processing {len(fastq_files)} FASTQ files")
        logger.info("")
        
        # Statistics
        stats = {
            'total': len(fastq_files),
            'submitted': 0,
            'skipped': 0,
            'failed': 0
        }
        
        # Process each file
        for idx, fastq in enumerate(fastq_files, 1):
            sample_code = fastq['sample_code']
            fastq_path = fastq['path']
            size_mb = fastq['size_mb']
            
            logger.info(f"\n[{idx}/{len(fastq_files)}] {sample_code}")
            logger.info(f"  Path: {fastq_path}")
            logger.info(f"  Size: {size_mb:.1f} MB")
            
            # Submit
            result = await self.submit_sample(sample_code, fastq_path)
            
            if result['success']:
                stats['submitted'] += 1
            else:
                reason = result['reason']
                if reason == 'exists' and skip_existing:
                    stats['skipped'] += 1
                else:
                    stats['failed'] += 1
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("  📊 BATCH PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"  Total:      {stats['total']}")
        logger.info(f"  ✓ Submitted: {stats['submitted']}")
        logger.info(f"  ⊘ Skipped:   {stats['skipped']}")
        logger.info(f"  ✗ Failed:    {stats['failed']}")
        logger.info("=" * 80)
        
        await self.close_db()


async def main():
    """Main entry point"""
    
    import argparse
    parser = argparse.ArgumentParser(
        description='Direct batch pipeline submission (bypasses API)'
    )
    parser.add_argument('--limit', type=int,
                       help='Limit number of samples to process')
    parser.add_argument('--dry-run', action='store_true',
                       help='List files without submitting')
    
    args = parser.parse_args()
    
    runner = DirectBatchRunner()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - Listing files only")
        await runner.init_db()
        files = runner.find_fastq_files()
        logger.info(f"\nFound {len(files)} FASTQ files:")
        for idx, f in enumerate(files[:30], 1):
            logger.info(f"  {idx:3d}. {f['sample_code']:15s} {f['size_mb']:8.1f} MB  {f['path']}")
        if len(files) > 30:
            logger.info(f"  ... and {len(files) - 30} more")
        await runner.close_db()
    else:
        await runner.process_batch(limit=args.limit)


if __name__ == '__main__':
    asyncio.run(main())

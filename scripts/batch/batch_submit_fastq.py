#!/usr/bin/env python3
"""
Batch FASTQ Submission Script
Submits all FASTQ files from data/ directory to the web platform API sequentially
"""

import os
import sys
import json
import time
import requests
import asyncio
import asyncpg
from pathlib import Path
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/batch_submit.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.getenv('API_URL', 'http://localhost:8000')
API_VERSION = 'v2'
DATA_DIR = Path('/home/nicolaedrabcinski/upgrade/data')
RESULTS_BASE = Path('/home/nicolaedrabcinski/upgrade/results')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', '5433')),
    'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
    'user': os.getenv('POSTGRES_USER', 'upgrade_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'upgrade_pass')
}

# Pipeline parameters (customize as needed)
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


class BatchFASTQSubmitter:
    """Batch processor for FASTQ files via web API"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.db_pool = None
        
    async def init_db(self):
        """Initialize database connection pool"""
        try:
            self.db_pool = await asyncpg.create_pool(**DB_CONFIG)
            logger.info("✓ Database connection established")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise
    
    async def close_db(self):
        """Close database connection pool"""
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
                    # Pattern: data/SRRXXXXXXX/raw/SRRXXXXXXX.fastq
                    rel_path = full_path.relative_to(DATA_DIR)
                    parts = rel_path.parts
                    
                    if len(parts) >= 1:
                        sample_code = parts[0]  # First directory is sample code
                        fastq_files.append({
                            'path': str(full_path),
                            'sample_code': sample_code,
                            'filename': file,
                            'size_mb': full_path.stat().st_size / 1024 / 1024
                        })
        
        logger.info(f"✓ Found {len(fastq_files)} FASTQ files")
        return fastq_files
    
    async def sample_exists(self, sample_code):
        """Check if sample already exists in database"""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT sample_id FROM samples WHERE sample_code = $1",
                sample_code
            )
            return result is not None
    
    async def create_sample(self, sample_code, fastq_path):
        """Create sample record in database"""
        async with self.db_pool.acquire() as conn:
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
                logger.info(f"  ✓ Created sample record: {sample_code} (ID: {sample_id})")
                return sample_id
            except Exception as e:
                logger.error(f"  ✗ Failed to create sample {sample_code}: {e}")
                return None
    
    async def pipeline_already_exists(self, sample_code):
        """Check if pipeline run already exists for this sample"""
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT pr.pipeline_id 
                FROM pipeline_runs pr
                JOIN samples s ON pr.sample_id = s.sample_id
                WHERE s.sample_code = $1
                AND pr.status IN ('queued', 'running', 'completed')
            """, sample_code)
            return result is not None
    
    async def submit_pipeline(self, sample_code, fastq_path, params=None):
        """Submit pipeline run via API"""
        
        # Check if pipeline already exists
        if await self.pipeline_already_exists(sample_code):
            logger.warning(f"  ⊘ Pipeline already exists for {sample_code}, skipping")
            return {'success': False, 'reason': 'already_exists'}
        
        # Ensure sample exists
        if not await self.sample_exists(sample_code):
            sample_id = await self.create_sample(sample_code, fastq_path)
            if not sample_id:
                return {'success': False, 'reason': 'sample_creation_failed'}
        
        # Prepare submission payload
        payload = {
            'sample_code': sample_code,
            'pipeline_name': 'nextflow_pipeline',
            'parameters': params or DEFAULT_PARAMS
        }
        
        try:
            url = f"{API_BASE_URL}/api/{API_VERSION}/pipeline/submit"
            logger.info(f"  → Submitting to {url}")
            
            response = self.session.post(url, json=payload, timeout=30)
            
            if response.status_code == 201:
                result = response.json()
                logger.info(
                    f"  ✓ Pipeline submitted: ID={result.get('pipeline_id')}, "
                    f"Job={result.get('job_id')}"
                )
                return {
                    'success': True,
                    'pipeline_id': result.get('pipeline_id'),
                    'job_id': result.get('job_id'),
                    'status': result.get('status')
                }
            else:
                error = response.text
                logger.error(f"  ✗ API error ({response.status_code}): {error}")
                return {'success': False, 'reason': 'api_error', 'details': error}
                
        except Exception as e:
            logger.error(f"  ✗ Submission failed: {e}")
            return {'success': False, 'reason': 'exception', 'details': str(e)}
    
    async def wait_for_pipeline(self, pipeline_id, timeout=3600):
        """Wait for pipeline to complete (optional)"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                url = f"{API_BASE_URL}/api/{API_VERSION}/pipeline/runs/{pipeline_id}"
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    
                    if status in ('completed', 'failed', 'cancelled'):
                        return status
                    
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.warning(f"  Status check error: {e}")
                await asyncio.sleep(30)
        
        return 'timeout'
    
    async def process_batch(self, wait_between=5, wait_for_completion=False):
        """Process all FASTQ files sequentially"""
        
        logger.info("=" * 80)
        logger.info("  🚀 BATCH FASTQ SUBMISSION")
        logger.info("=" * 80)
        
        # Initialize database
        await self.init_db()
        
        # Find all FASTQ files
        fastq_files = self.find_fastq_files()
        
        if not fastq_files:
            logger.warning("No FASTQ files found!")
            await self.close_db()
            return
        
        logger.info(f"\n📊 Processing {len(fastq_files)} FASTQ files")
        logger.info(f"   Wait between submissions: {wait_between}s")
        logger.info(f"   Wait for completion: {wait_for_completion}")
        logger.info("")
        
        # Statistics
        stats = {
            'total': len(fastq_files),
            'submitted': 0,
            'skipped': 0,
            'failed': 0,
            'completed': 0
        }
        
        # Process each file
        for idx, fastq in enumerate(fastq_files, 1):
            sample_code = fastq['sample_code']
            fastq_path = fastq['path']
            size_mb = fastq['size_mb']
            
            logger.info(f"\n[{idx}/{len(fastq_files)}] Processing: {sample_code}")
            logger.info(f"  Path: {fastq_path}")
            logger.info(f"  Size: {size_mb:.1f} MB")
            
            # Submit pipeline
            result = await self.submit_pipeline(sample_code, fastq_path)
            
            if result['success']:
                stats['submitted'] += 1
                
                # Optionally wait for completion
                if wait_for_completion and result.get('pipeline_id'):
                    logger.info(f"  ⏳ Waiting for pipeline {result['pipeline_id']} to complete...")
                    final_status = await self.wait_for_pipeline(result['pipeline_id'])
                    logger.info(f"  ✓ Pipeline finished with status: {final_status}")
                    
                    if final_status == 'completed':
                        stats['completed'] += 1
            else:
                reason = result.get('reason')
                if reason == 'already_exists':
                    stats['skipped'] += 1
                else:
                    stats['failed'] += 1
            
            # Wait between submissions
            if idx < len(fastq_files) and not wait_for_completion:
                logger.info(f"  💤 Waiting {wait_between}s before next submission...")
                await asyncio.sleep(wait_between)
        
        # Final statistics
        logger.info("\n" + "=" * 80)
        logger.info("  📊 BATCH PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"  Total files:    {stats['total']}")
        logger.info(f"  ✓ Submitted:    {stats['submitted']}")
        logger.info(f"  ⊘ Skipped:      {stats['skipped']}")
        logger.info(f"  ✗ Failed:       {stats['failed']}")
        if wait_for_completion:
            logger.info(f"  ✓ Completed:    {stats['completed']}")
        logger.info("=" * 80)
        
        # Close database
        await self.close_db()


async def main():
    """Main entry point"""
    
    import argparse
    parser = argparse.ArgumentParser(description='Batch submit FASTQ files to pipeline API')
    parser.add_argument('--wait', type=int, default=5,
                       help='Seconds to wait between submissions (default: 5)')
    parser.add_argument('--wait-completion', action='store_true',
                       help='Wait for each pipeline to complete before submitting next')
    parser.add_argument('--api-url', default='http://localhost:8000',
                       help='API base URL (default: http://localhost:8000)')
    parser.add_argument('--dry-run', action='store_true',
                       help='List files without submitting')
    
    args = parser.parse_args()
    
    # Update global config
    global API_BASE_URL
    API_BASE_URL = args.api_url
    
    submitter = BatchFASTQSubmitter()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - Listing files only")
        await submitter.init_db()
        files = submitter.find_fastq_files()
        logger.info(f"\nFound {len(files)} FASTQ files:")
        for f in files[:20]:  # Show first 20
            logger.info(f"  - {f['sample_code']}: {f['path']} ({f['size_mb']:.1f} MB)")
        if len(files) > 20:
            logger.info(f"  ... and {len(files) - 20} more")
        await submitter.close_db()
    else:
        await submitter.process_batch(
            wait_between=args.wait,
            wait_for_completion=args.wait_completion
        )


if __name__ == '__main__':
    asyncio.run(main())

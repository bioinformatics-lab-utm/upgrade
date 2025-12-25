#!/usr/bin/env python3
"""
Import old pipeline results from /results/ directory into database.
Scans for directories with summary JSON files and creates pipeline_runs entries.
"""

import os
import json
import asyncio
import asyncpg
from datetime import datetime
from pathlib import Path

# Database configuration
DB_HOST = 'postgres'
DB_PORT = 5432
DB_NAME = 'upgrade_db'
DB_USER = 'upgrade'
DB_PASSWORD = 'tZJu5gULroNURCZm6Bj8owOhRmKjfBkLhaqS2H64BGk='

RESULTS_DIR = '/results'

async def connect_db():
    """Connect to PostgreSQL database"""
    return await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

async def get_or_create_sample(conn, sample_code, sample_type='nanopore'):
    """Get existing sample or create new one"""
    # Check if sample exists
    sample = await conn.fetchrow(
        "SELECT sample_id FROM samples WHERE sample_code = $1",
        sample_code
    )
    
    if sample:
        return sample['sample_id']
    
    # Create new sample
    sample_id = await conn.fetchval("""
        INSERT INTO samples (
            sample_code, sample_type, sequencing_platform, 
            collection_date, created_at
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING sample_id
    """, sample_code, sample_type, 'Oxford Nanopore', 
        datetime.now().date(), datetime.now())
    
    print(f"  ✓ Created sample: {sample_code} (ID: {sample_id})")
    return sample_id

async def import_result_directory(conn, result_dir):
    """Import a single result directory"""
    dir_name = os.path.basename(result_dir.rstrip('/'))
    
    # Find summary JSON file
    summary_file = None
    for pattern in ['00_summary/*_summary.json', '*_summary.json']:
        matches = list(Path(result_dir).glob(pattern))
        if matches:
            summary_file = matches[0]
            break
    
    if not summary_file:
        print(f"  ⚠ No summary file found in {dir_name}")
        return None
    
    # Read summary data
    try:
        with open(summary_file) as f:
            summary = json.load(f)
    except Exception as e:
        print(f"  ✗ Failed to read {summary_file}: {e}")
        return None
    
    sample_code = summary.get('sample_id', dir_name)
    
    # Check if pipeline run already exists
    existing = await conn.fetchrow(
        "SELECT run_id FROM pipeline_runs WHERE sample_code = $1 OR results_path = $2",
        sample_code, result_dir
    )
    
    if existing:
        print(f"  ⊘ Already exists: {sample_code}")
        return None
    
    # Get or create sample
    sample_id = await get_or_create_sample(conn, sample_code)
    
    # Extract metrics from summary
    quality_score = summary.get('quality_score', 0)
    amr_risk_score = summary.get('amr_risk_score', 0)
    
    mags = summary.get('mags', {})
    total_bins = mags.get('total_bins', 0)
    high_quality_mags = mags.get('high_quality', 0)
    
    amr = summary.get('amr', {})
    total_arg_genes = amr.get('total_arg_genes', 0)
    
    # Get creation time from directory or file
    try:
        dir_stat = os.stat(result_dir)
        created_at = datetime.fromtimestamp(dir_stat.st_ctime)
    except:
        created_at = datetime.now()
    
    # Check if log file exists
    log_file = os.path.join(result_dir, 'nextflow.log')
    if not os.path.exists(log_file):
        log_file = None
    
    # Determine status (if has summary, it's completed)
    status = 'completed'
    
    # Insert pipeline run
    run_id = await conn.fetchval("""
        INSERT INTO pipeline_runs (
            sample_id, pipeline_name, pipeline_version, status,
            results_path, log_file_path, sample_code,
            parameters, created_at, queued_at, started_at, completed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9, $9, $9)
        RETURNING run_id
    """, sample_id, 'nextflow_pipeline', summary.get('pipeline_version', '1.0'),
        status, result_dir, log_file, sample_code, 
        json.dumps({}), created_at)
    
    print(f"  ✓ Imported: {sample_code} (Run ID: {run_id}, Quality: {quality_score:.1f}, MAGs: {total_bins}, AMR: {total_arg_genes})")
    
    return run_id

async def main():
    """Main import function"""
    print("🔍 Scanning results directory...")
    
    # Get all result directories
    result_dirs = [
        d for d in Path(RESULTS_DIR).iterdir()
        if d.is_dir() and d.name != 'minio'
    ]
    
    print(f"📁 Found {len(result_dirs)} result directories")
    
    # Connect to database
    print("🔌 Connecting to database...")
    conn = await connect_db()
    
    try:
        imported = 0
        skipped = 0
        failed = 0
        
        for result_dir in sorted(result_dirs):
            try:
                result = await import_result_directory(conn, str(result_dir))
                if result:
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"  ✗ Error importing {result_dir.name}: {e}")
                failed += 1
        
        print("\n" + "="*60)
        print(f"✅ Import complete!")
        print(f"   Imported: {imported}")
        print(f"   Skipped:  {skipped}")
        print(f"   Failed:   {failed}")
        print("="*60)
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

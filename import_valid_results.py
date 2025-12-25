#!/usr/bin/env python3
"""
Import valid pipeline results into database
"""
import json
import asyncio
import asyncpg
import os
from pathlib import Path
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'postgres',  # Docker service name
    'port': 5432,
    'database': 'upgrade_db',
    'user': 'upgrade',
    'password': os.environ.get('POSTGRES_PASSWORD', 'upgrade_password')
}

async def import_results():
    # Load valid runs
    valid_runs_file = Path('/results/valid_runs_for_import.json')
    if not valid_runs_file.exists():
        print("❌ valid_runs_for_import.json not found!")
        return
    
    with open(valid_runs_file, 'r') as f:
        valid_runs = json.load(f)
    
    print(f"Found {len(valid_runs)} valid runs to import")
    
    # Connect to database
    conn = await asyncpg.connect(**DB_CONFIG)
    
    try:
        imported = 0
        skipped = 0
        
        for run in valid_runs:
            sample_code = run['name']
            
            # Check if already exists
            existing = await conn.fetchrow(
                "SELECT sample_id FROM samples WHERE sample_code = $1",
                sample_code
            )
            
            if existing:
                print(f"⏭️  Skipping {sample_code} - already in database")
                skipped += 1
                continue
            
            # Insert sample
            sample_id = await conn.fetchval("""
                INSERT INTO samples (
                    sample_code, sample_type, sequencing_platform,
                    collection_date, created_at
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING sample_id
            """, sample_code, 'nanopore', 'Oxford Nanopore', 
                datetime.now().date(), datetime.now())
            
            # Insert pipeline run
            pipeline_run_id = await conn.fetchval("""
                INSERT INTO pipeline_runs (
                    sample_id, pipeline_name, pipeline_version,
                    status, results_path, 
                    queued_at, started_at, completed_at, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING pipeline_id
            """, sample_id, 'nextflow_pipeline', run['pipeline_version'],
                'completed', f"/results/{sample_code}",
                datetime.now(), datetime.now(), datetime.now(), datetime.now())
            
            print(f"✅ Imported {sample_code} (sample_id={sample_id}, pipeline_id={pipeline_run_id})")
            imported += 1
        
        print(f"\n✅ Import complete!")
        print(f"   Imported: {imported}")
        print(f"   Skipped (already exists): {skipped}")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(import_results())

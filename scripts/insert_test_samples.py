#!/usr/bin/env python3
"""
Quick test - insert 3 small test samples into queue
"""

import psycopg2
import os
import json
from pathlib import Path

# Load samples from JSON file
samples_file = Path('/tmp/batch_test_samples.json')
if samples_file.exists():
    with open(samples_file, 'r') as f:
        data = json.load(f)
        TEST_SAMPLES = data['samples']
        # Add missing fields with defaults
        for sample in TEST_SAMPLES:
            sample.setdefault('organism', 'wastewater metagenome')
            sample.setdefault('collection_date', '2024')
            sample.setdefault('library_strategy', 'METAGENOMIC')
            sample.setdefault('platform', 'ILLUMINA')
            sample.setdefault('instrument', 'Illumina')
else:
    print(f"Error: {samples_file} not found")
    exit(1)

db_config = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'upgrade_db'),
    'user': os.getenv('POSTGRES_USER', 'upgrade'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}

try:
    conn = psycopg2.connect(**db_config)
    print("✓ Connected to database")
    
    with conn.cursor() as cur:
        # Create table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sample_queue (
                id SERIAL PRIMARY KEY,
                accession VARCHAR(50) UNIQUE NOT NULL,
                latitude FLOAT,
                longitude FLOAT,
                file_size_mb FLOAT,
                country VARCHAR(100),
                collection_date VARCHAR(50),
                library_strategy VARCHAR(100),
                platform VARCHAR(100),
                instrument VARCHAR(100),
                organism VARCHAR(200),
                geo_loc_name VARCHAR(200),
                status VARCHAR(20) DEFAULT 'pending',
                download_started_at TIMESTAMP,
                download_completed_at TIMESTAMP,
                pipeline_started_at TIMESTAMP,
                pipeline_completed_at TIMESTAMP,
                quality_score FLOAT,
                amr_risk_score FLOAT,
                summary_json_path TEXT,
                error_message TEXT,
                retry_count INT DEFAULT 0,
                last_attempt_at TIMESTAMP,
                full_metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_sample_queue_status ON sample_queue(status);
            CREATE INDEX IF NOT EXISTS idx_sample_queue_file_size ON sample_queue(file_size_mb);
        """)
        print("✓ Table created/verified")
        
        # Insert samples
        inserted = 0
        for sample in TEST_SAMPLES:
            try:
                cur.execute("""
                    INSERT INTO sample_queue 
                    (accession, latitude, longitude, file_size_mb, country, 
                     collection_date, library_strategy, platform, instrument,
                     organism, geo_loc_name, status, full_metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    ON CONFLICT (accession) 
                    DO UPDATE SET 
                        status = 'pending',
                        retry_count = 0,
                        error_message = NULL,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    sample['run_id'],
                    sample['lat'],
                    sample['lon'],
                    sample['file_size_mb'],
                    sample['country'],
                    sample['collection_date'],
                    sample['library_strategy'],
                    sample['platform'],
                    sample['instrument'],
                    sample['organism'],
                    sample['geo_loc_name'],
                    json.dumps(sample)
                ))
                inserted += 1
                print(f"  ✓ {sample['run_id']}: {sample['file_size_mb']}MB - {sample['geo_loc_name']}")
            except Exception as e:
                print(f"  ✗ {sample['run_id']}: {e}")
        
        conn.commit()
        print(f"\n✅ Inserted {inserted}/{len(TEST_SAMPLES)} samples")
        
        # Show queue
        cur.execute("""
            SELECT accession, file_size_mb, geo_loc_name, status
            FROM sample_queue
            ORDER BY file_size_mb ASC
        """)
        
        print("\n=== Sample Queue ===")
        for row in cur.fetchall():
            acc, size, loc, status = row
            print(f"{acc}: {size:.1f}MB - {loc} [{status}]")
        
    conn.close()
    
    print("\n" + "="*80)
    print("✅ Test samples ready!")
    print("="*80)
    print("\nNext steps:")
    print("1. Check queue:")
    print("   docker exec upgrade_postgres psql -U upgrade -d upgrade_db \\")
    print("     -c 'SELECT accession, file_size_mb, geo_loc_name FROM sample_queue ORDER BY file_size_mb;'")
    print("\n2. Run batch processor (3 samples):")
    print("   docker exec upgrade_rq_worker python3 /app/sra_batch_processor.py 3")
    print("\n   Or copy script to container first:")
    print("   docker cp scripts/sra_batch_processor.py upgrade_rq_worker:/app/")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

#!/usr/bin/env python3
"""
Queue ONT samples from geocoded JSON to PostgreSQL sample_queue
Manages batch processing with 20GB concurrent limit
"""

import json
import sys
import subprocess
from pathlib import Path

def exec_sql(query, params=None):
    """Execute SQL via docker exec"""
    if params:
        # Simple parameter substitution for INSERT
        for param in params:
            query = query.replace('?', str(param), 1)
    
    cmd = [
        'docker', 'exec', '-i', 'upgrade_postgres',
        'psql', '-U', 'upgrade', '-d', 'upgrade_db',
        '-t', '-A', '-c', query
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SQL Error: {result.stderr}")
        return None
    return result.stdout.strip()

def insert_samples(samples):
    """Insert samples into queue"""
    print(f"Inserting {len(samples)} samples into queue...")
    
    inserted = 0
    skipped = 0
    
    for sample in samples:
        accession = sample['run_id']
        size_mb = sample['file_size_mb']
        lat = sample.get('lat', 'NULL')
        lon = sample.get('lon', 'NULL')
        
        # Skip if no valid coordinates
        if lat in ['N/A', 'NULL'] or lon in ['N/A', 'NULL']:
            print(f"  ⊘ {accession}: No coordinates, skipping")
            skipped += 1
            continue
        
        try:
            lat = float(lat)
            lon = float(lon)
        except:
            print(f"  ⊘ {accession}: Invalid coordinates, skipping")
            skipped += 1
            continue
        
        # Check if already exists
        check = exec_sql(f"SELECT accession FROM sample_queue WHERE accession = '{accession}';")
        if check and check.strip():
            print(f"  → {accession}: Already in queue")
            continue
        
        # Insert
        query = f"""
        INSERT INTO sample_queue (accession, latitude, longitude, file_size_mb, status)
        VALUES ('{accession}', {lat}, {lon}, {size_mb}, 'pending')
        ON CONFLICT (accession) DO NOTHING;
        """
        
        result = exec_sql(query)
        if result is not None:
            print(f"  ✓ {accession}: {size_mb:.1f} MB at ({lat:.4f}, {lon:.4f})")
            inserted += 1
        else:
            print(f"  ✗ {accession}: Failed to insert")
    
    print(f"\n✓ Inserted: {inserted}")
    print(f"⊘ Skipped: {skipped}")
    return inserted

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 queue_ont_samples.py <geocoded_json>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    
    print("="*80)
    print("ONT Sample Queue Manager")
    print("="*80)
    
    # Load samples
    with open(json_file) as f:
        data = json.load(f)
    
    if 'samples' in data:
        samples = data['samples']
    else:
        samples = data
    
    print(f"\n✓ Loaded {len(samples)} samples from {json_file}")
    
    # Show stats
    total_size = sum(s['file_size_mb'] for s in samples) / 1024
    print(f"  Total size: {total_size:.1f} GB")
    print(f"  Size range: {min(s['file_size_mb'] for s in samples):.1f} - {max(s['file_size_mb'] for s in samples):.1f} MB")
    
    # Insert into queue
    inserted = insert_samples(samples)
    
    if inserted > 0:
        print(f"\n{'='*80}")
        print("Queue Status")
        print("="*80)
        
        # Show queue stats
        stats = exec_sql("""
            SELECT status, COUNT(*), ROUND(SUM(file_size_mb)/1024, 1) 
            FROM sample_queue 
            GROUP BY status 
            ORDER BY status;
        """)
        
        if stats:
            print(f"\n{'Status':<15} {'Count':<10} {'Size (GB)'}")
            print("-"*40)
            for line in stats.split('\n'):
                if line.strip():
                    parts = line.split('|')
                    if len(parts) == 3:
                        print(f"{parts[0]:<15} {parts[1]:<10} {parts[2]}")
        
        print(f"\n{'='*80}")
        print("To start processing with 20GB limit:")
        print("="*80)
        print("python3 scripts/host_batch_processor.py --max-concurrent-gb 20")

if __name__ == '__main__':
    main()

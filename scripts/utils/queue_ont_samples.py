#!/usr/bin/env python3
"""
Queue ONT samples from geocoded JSON to PostgreSQL sample_queue
Manages batch processing with 20GB concurrent limit

SECURITY NOTE: This script uses psycopg2 with parameterized queries
to prevent SQL injection vulnerabilities.
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql


def get_db_connection():
    """
    Get a database connection using environment variables or defaults.
    Returns a psycopg2 connection object.
    """
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        database=os.environ.get("POSTGRES_DB", "upgrade_db"),
        user=os.environ.get("POSTGRES_USER", "upgrade"),
        password=os.environ.get("POSTGRES_PASSWORD", "upgrade"),
    )


def exec_sql(query, params=None, fetch=True):
    """
    Execute SQL using psycopg2 with parameterized queries.
    
    Args:
        query: SQL query string with %s placeholders for parameters
        params: tuple of parameters (optional)
        fetch: if True, return fetched results; if False, return row count
    
    Returns:
        Query results as string (for compatibility) or None on error
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                rows = cur.fetchall()
                # Return as newline-separated pipe-delimited string for compatibility
                if rows:
                    return "\n".join("|".join(str(col) for col in row) for row in rows)
                return ""
            else:
                conn.commit()
                return str(cur.rowcount)
    except psycopg2.Error as e:
        print(f"SQL Error: {e}")
        return None
    finally:
        if conn:
            conn.close()


def insert_samples(samples):
    """Insert samples into queue using parameterized queries."""
    print(f"Inserting {len(samples)} samples into queue...")
    
    inserted = 0
    skipped = 0
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
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
                except (ValueError, TypeError):
                    print(f"  ⊘ {accession}: Invalid coordinates, skipping")
                    skipped += 1
                    continue
                
                # Check if already exists - parameterized query
                cur.execute(
                    "SELECT accession FROM sample_queue WHERE accession = %s",
                    (accession,)
                )
                if cur.fetchone():
                    print(f"  → {accession}: Already in queue")
                    continue
                
                # Insert with parameterized query - safe from SQL injection
                cur.execute(
                    """
                    INSERT INTO sample_queue (accession, latitude, longitude, file_size_mb, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                    ON CONFLICT (accession) DO NOTHING
                    """,
                    (accession, lat, lon, size_mb)
                )
                
                if cur.rowcount > 0:
                    print(f"  ✓ {accession}: {size_mb:.1f} MB at ({lat:.4f}, {lon:.4f})")
                    inserted += 1
                else:
                    print(f"  → {accession}: Already in queue (conflict)")
            
            conn.commit()
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
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
        
        # Show queue stats using parameterized query
        stats = exec_sql(
            """
            SELECT status, COUNT(*), ROUND(SUM(file_size_mb)/1024, 1) 
            FROM sample_queue 
            GROUP BY status 
            ORDER BY status
            """
        )
        
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

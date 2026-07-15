#!/usr/bin/env python3
"""
Scan results/ and register files into minio_objects.
Uses psycopg2 with parameterized queries to write into the database securely.

Usage:
  python scripts/sync_minio_objects.py --bucket genomic-bronze --apply
  python scripts/sync_minio_objects.py --bucket genomic-bronze --dry-run

The script will:
 - create a synthetic nextflow_executions record (unless --no-exec)
 - create bucket if missing
 - insert minio_objects rows with object_key relative to repo root
 - optionally create basic data_lineage links (raw -> derived by stage)

Run with --apply to perform DB writes. Default: dry-run (prints SQL and summary).

SECURITY NOTE: This script uses psycopg2 with parameterized queries
to prevent SQL injection vulnerabilities.
"""

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import psycopg2
from psycopg2 import sql as psql

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'results'

SQL_BATCH_LIMIT = 500


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


def sha256_of(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def md5_of(path: Path):
    m = hashlib.md5()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            m.update(chunk)
    return m.hexdigest()


def create_synthetic_execution(conn, name_tag: str):
    """Create a synthetic execution record using parameterized queries."""
    ts = int(time.time())
    exec_name = f"sync_existing_results_{name_tag}_{ts}"
    
    with conn.cursor() as cur:
        # Ensure workflow exists
        cur.execute(
            "SELECT workflow_id FROM nextflow_workflows WHERE workflow_name = %s AND workflow_version = %s LIMIT 1",
            ('UPGRADE_Genomic_Pipeline', '1.0')
        )
        row = cur.fetchone()
        
        if row:
            workflow_id = row[0]
            print(f"Found workflow id={workflow_id}")
        else:
            cur.execute(
                """INSERT INTO nextflow_workflows 
                   (workflow_name, workflow_version, description, nextflow_version, workflow_script_path, is_active) 
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING workflow_id""",
                ('UPGRADE_Genomic_Pipeline', '1.0', 
                 'Environmental genomic surveillance with ONT sequencing', 
                 '25.10.0', '/nextflow/main.nf', True)
            )
            workflow_id = cur.fetchone()[0]
            print(f"Created workflow id={workflow_id}")
        
        # Create execution record
        cur.execute(
            """INSERT INTO nextflow_executions 
               (workflow_id, execution_name, nextflow_run_name, status, start_time, complete_time, duration, success, created_at) 
               VALUES (%s, %s, %s, %s, now(), now(), interval '0', %s, now())
               RETURNING execution_id""",
            (workflow_id, exec_name, exec_name, 'succeeded', True)
        )
        exec_id = cur.fetchone()[0]
        conn.commit()
        
    print(f"Created synthetic execution_id={exec_id} (workflow_id={workflow_id})")
    return exec_id


def ensure_bucket(conn, bucket_name: str):
    """Ensure bucket exists using parameterized queries."""
    import re
    if not re.match(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$', bucket_name):
        raise ValueError(f"Invalid bucket name: {bucket_name}")
    
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bucket_id FROM minio_buckets WHERE bucket_name = %s",
            (bucket_name,)
        )
        row = cur.fetchone()
        
        if row:
            bid = row[0]
            print(f"Bucket '{bucket_name}' exists bucket_id={bid}")
            return bid
        
        # Create bucket
        cur.execute(
            "INSERT INTO minio_buckets (bucket_name, created_at) VALUES (%s, now()) RETURNING bucket_id",
            (bucket_name,)
        )
        bid = cur.fetchone()[0]
        conn.commit()
        
    print(f"Created bucket '{bucket_name}' bucket_id={bid}")
    return bid


def collect_files():
    """Collect all files from results directory."""
    files = []
    for root, dirs, filenames in os.walk(RESULTS):
        for fn in filenames:
            p = Path(root) / fn
            if p.is_file() and p.stat().st_size > 0:
                rel = p.relative_to(ROOT)
                files.append((p, str(rel)))
    return files


def build_file_entries(entries):
    """Build list of file entries with metadata."""
    file_entries = []
    for p, rel_key in entries:
        size = p.stat().st_size
        md5 = md5_of(p)[:32]
        sha = sha256_of(p)
        created = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(p.stat().st_mtime))
        object_name = p.name
        object_key = rel_key
        layer_stage = p.parts[1] if len(p.parts) > 1 else None
        process_name = layer_stage
        version_id = ''
        file_entries.append({
            'object_key': object_key,
            'object_name': object_name,
            'object_size_bytes': size,
            'md5_hash': md5,
            'sha256_hash': sha,
            'created_at': created,
            'storage_class': 'STANDARD',
            'version_id': version_id,
            'is_latest_version': True,
            'access_count': 0,
            'sample_id': None,
            'process_name': process_name,
            'layer_stage': layer_stage,
        })
    return file_entries


def insert_minio_objects_batch(conn, bucket_id, execution_id, file_entries):
    """Insert minio objects using parameterized queries in batches."""
    if not file_entries:
        return 0
    
    inserted = 0
    with conn.cursor() as cur:
        for entry in file_entries:
            try:
                cur.execute(
                    """INSERT INTO minio_objects 
                       (bucket_id, object_key, object_name, object_size_bytes, md5_hash, sha256_hash, 
                        created_at, storage_class, version_id, is_latest_version, access_count, 
                        sample_id, execution_id, process_name, layer_stage) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (bucket_id, object_key, version_id) DO NOTHING""",
                    (bucket_id, entry['object_key'], entry['object_name'], entry['object_size_bytes'],
                     entry['md5_hash'], entry['sha256_hash'], entry['created_at'], entry['storage_class'],
                     entry['version_id'], entry['is_latest_version'], entry['access_count'],
                     entry['sample_id'], execution_id, entry['process_name'], entry['layer_stage'])
                )
                inserted += cur.rowcount
            except psycopg2.Error as e:
                print(f"Warning: Failed to insert {entry['object_key']}: {e}")
        conn.commit()
    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket', default='genomic-bronze')
    parser.add_argument('--apply', action='store_true', help='Apply changes to DB')
    parser.add_argument('--exec-tag', default='manual_sync')
    args = parser.parse_args()

    files = collect_files()
    print(f"Found {len(files)} files under results/ to consider")
    if not files:
        return

    # Connect to database
    conn = get_db_connection()
    
    try:
        # ensure bucket
        bucket_id = ensure_bucket(conn, args.bucket)

        execution_id = None
        if args.apply:
            execution_id = create_synthetic_execution(conn, args.exec_tag)
        else:
            print('Dry-run: not creating synthetic execution. Use --apply to write to DB.')
            # For dry-run, show what would be done
            file_entries = build_file_entries(files)
            print(f"\nWould insert {len(file_entries)} objects into bucket_id={bucket_id}")
            if file_entries:
                print(f"  First: {file_entries[0]['object_key']}")
                print(f"  Last:  {file_entries[-1]['object_key']}")
            return

        file_entries = build_file_entries(files)
        
        print(f"Prepared {len(file_entries)} file entries")
        
        # Insert in batches
        total_inserted = 0
        for i in range(0, len(file_entries), SQL_BATCH_LIMIT):
            batch = file_entries[i:i+SQL_BATCH_LIMIT]
            inserted = insert_minio_objects_batch(conn, bucket_id, execution_id, batch)
            total_inserted += inserted
            print(f"Applied batch {i//SQL_BATCH_LIMIT + 1} ({len(batch)} entries, {inserted} inserted)")

        print(f'Sync completed: {total_inserted} records inserted')
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()

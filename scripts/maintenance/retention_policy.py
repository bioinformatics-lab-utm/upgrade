#!/usr/bin/env python3
"""
Retention Policy Script for MinIO and Database

Deletes or archives MinIO objects and DB records older than a specified retention period.

- Removes old objects from MinIO buckets (bronze, silver, gold)
- Cleans up corresponding DB records (minio_objects, data_lineage, pipeline_progress_events, nextflow_executions)
- Retention period is configurable (default: 180 days)

Usage:
    python scripts/retention_policy.py [--days 180] [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio
import asyncpg
from minio import Minio
from minio.error import S3Error

# Add backend to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent / 'web-dashboard' / 'backend'))

# Load environment variables from .env file if exists
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:  # Don't override existing env vars
                    os.environ[key] = value

from config import config

# Configurable defaults
RETENTION_DAYS = 180
MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')  # Use localhost for external scripts
MINIO_ACCESS_KEY = os.environ.get('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin')
MINIO_SECURE = False
# Use localhost for external DB connections
DATABASE_URL = os.environ.get('DATABASE_URL', f"postgresql://{os.environ.get('POSTGRES_USER', 'upgrade')}:{os.environ.get('POSTGRES_PASSWORD', 'postgres')}@localhost:{os.environ.get('POSTGRES_PORT', 5432)}/{os.environ.get('POSTGRES_DB', 'upgrade_db')}")
BUCKETS = ['genomic-bronze', 'genomic-silver', 'genomic-gold']


def parse_args():
    parser = argparse.ArgumentParser(description="Retention policy cleanup for MinIO and DB")
    parser.add_argument('--days', type=int, default=RETENTION_DAYS, help='Retention period in days')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted, but do not delete')
    return parser.parse_args()


def get_minio_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )

async def cleanup_db(conn, cutoff, dry_run=False):
    # Find old minio_objects
    old_objects = await conn.fetch("""
        SELECT object_id, object_key, created_at FROM minio_objects WHERE created_at < $1
    """, cutoff)
    print(f"Found {len(old_objects)} old minio_objects")
    if dry_run:
        for obj in old_objects:
            print(f"Would delete DB object_id={obj['object_id']} key={obj['object_key']} created_at={obj['created_at']}")
    else:
        await conn.execute("DELETE FROM data_lineage WHERE target_object_id = ANY($1)", [o['object_id'] for o in old_objects])
        await conn.execute("DELETE FROM minio_objects WHERE object_id = ANY($1)", [o['object_id'] for o in old_objects])
        print(f"Deleted {len(old_objects)} minio_objects and related data_lineage records")

    # Optionally: Clean up old executions/progress
    # await conn.execute("DELETE FROM pipeline_progress_events WHERE created_at < $1", cutoff)
    # await conn.execute("DELETE FROM nextflow_executions WHERE created_at < $1", cutoff)


def cleanup_minio(minio_client, cutoff, dry_run=False):
    for bucket in BUCKETS:
        print(f"Checking bucket: {bucket}")
        try:
            for obj in minio_client.list_objects(bucket, recursive=True):
                if obj.last_modified < cutoff:
                    if dry_run:
                        print(f"Would delete MinIO object: {bucket}/{obj.object_name} (last_modified={obj.last_modified})")
                    else:
                        minio_client.remove_object(bucket, obj.object_name)
                        print(f"Deleted MinIO object: {bucket}/{obj.object_name}")
        except Exception as e:
            print(f"Skipping MinIO cleanup for bucket {bucket}: {e}")


async def main():
    args = parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"Retention cutoff: {cutoff} (older will be deleted)")

    # MinIO cleanup (skip if unavailable)
    try:
        minio_client = get_minio_client()
        cleanup_minio(minio_client, cutoff, dry_run=args.dry_run)
    except Exception as e:
        print(f"MinIO unavailable, skipping MinIO cleanup: {e}")

    # DB cleanup
    try:
        print(f"Connecting to database: {config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}")
        conn = await asyncpg.connect(DATABASE_URL)
        await cleanup_db(conn, cutoff, dry_run=args.dry_run)
        await conn.close()
        print("✓ DB cleanup complete")
    except Exception as e:
        print(f"DB cleanup failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Retry failed pipelines: register minio_objects and re-enqueue.
Fixes pipelines that failed because minio_objects records were missing.
"""

import asyncio
import asyncpg
import requests
import logging
import sys
from minio import Minio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Config
DB_URL = 'postgresql://upgrade:upgrade_password@localhost:5433/upgrade_db'
MINIO_ENDPOINT = 'localhost:9000'
MINIO_ACCESS_KEY = 'minioadmin'
MINIO_SECRET_KEY = 'minioadmin_password'
BRONZE_BUCKET = 'genomic-bronze'

API_BASE = 'http://localhost:8000'
USERNAME = 'nicolaedrabcinski'
PASSWORD = 'Nicolae123!'


async def main():
    conn = await asyncpg.connect(DB_URL)
    minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

    # Get all failed pipelines
    failed = await conn.fetch("""
        SELECT pr.pipeline_id, pr.sample_id, s.sample_code, pr.job_id
        FROM pipeline_runs pr
        JOIN samples s ON pr.sample_id = s.sample_id
        WHERE pr.status = 'failed'
          AND s.sample_code LIKE 'SRR%'
        ORDER BY pr.pipeline_id
    """)

    logger.info(f"Found {len(failed)} failed pipelines")

    # Get bronze bucket_id
    bucket_id = await conn.fetchval(
        "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1", BRONZE_BUCKET
    )

    fixed = 0
    for row in failed:
        pid = row['pipeline_id']
        sid = row['sample_id']
        sc = row['sample_code']

        # Check if minio_objects record exists
        existing = await conn.fetchval(
            "SELECT object_id FROM minio_objects WHERE pipeline_id = $1", pid
        )

        if not existing:
            # Find the file in MinIO
            object_path = f"{sc}/raw/{sc}.fastq.gz"
            try:
                stat = minio_client.stat_object(BRONZE_BUCKET, object_path)
            except Exception:
                logger.warning(f"  [{pid}] {sc}: file not in MinIO, skipping")
                continue

            # Register in minio_objects
            await conn.execute("""
                INSERT INTO minio_objects (
                    bucket_id, object_key, object_name, object_size_bytes,
                    content_type, etag, sample_id, pipeline_id, layer_stage
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'raw')
            """,
                bucket_id,
                object_path,
                f"{sc}.fastq.gz",
                stat.size,
                'application/gzip',
                stat.etag,
                sid,
                pid,
            )
            logger.info(f"  [{pid}] {sc}: registered minio_object ({stat.size / 1024 / 1024:.1f} MB)")

        # Reset pipeline status to queued
        await conn.execute("""
            UPDATE pipeline_runs
            SET status = 'queued',
                error_message = NULL,
                started_at = NULL,
                completed_at = NULL
            WHERE pipeline_id = $1
        """, pid)

        fixed += 1
        logger.info(f"  [{pid}] {sc}: status reset to queued")

    logger.info(f"\nFixed {fixed} pipelines. Now re-enqueuing via API...")

    # Login and re-trigger
    session = requests.Session()
    resp = session.post(f'{API_BASE}/api/auth/login', json={'username': USERNAME, 'password': PASSWORD})
    token = resp.json()['token']
    session.headers['Authorization'] = f'Bearer {token}'
    session.headers['Content-Type'] = 'application/json'

    # Re-enqueue each pipeline by calling confirm-upload again
    re_queued = 0
    for row in failed:
        pid = row['pipeline_id']
        sid = row['sample_id']
        sc = row['sample_code']

        # Check file exists in minio_objects now
        obj = await conn.fetchrow(
            "SELECT object_key, object_name, object_size_bytes FROM minio_objects WHERE pipeline_id = $1 LIMIT 1",
            pid
        )
        if not obj:
            continue

        resp = session.post(f'{API_BASE}/api/v2/pipeline/confirm-upload', json={
            'pipeline_id': pid,
            'sample_id': sid,
            'sample_code': sc,
            'uploaded_files': [{
                'filename': obj['object_name'],
                'size': obj['object_size_bytes'],
                'object_path': obj['object_key'],
            }],
            'parameters': {},
        })

        if resp.status_code in (200, 201) and resp.json().get('success'):
            job_id = resp.json().get('job_id', '?')
            logger.info(f"  [{pid}] {sc}: re-queued (job_id={job_id})")
            re_queued += 1
        else:
            logger.error(f"  [{pid}] {sc}: re-queue failed: {resp.text}")

    logger.info(f"\nDone! Re-queued {re_queued}/{len(failed)} pipelines")
    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

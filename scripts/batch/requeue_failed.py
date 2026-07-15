#!/usr/bin/env python3
"""Re-queue all failed pipeline runs using existing MinIO files."""

import sys
import os
import asyncio
import asyncpg
import logging

sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_DB   = os.getenv('POSTGRES_DB', 'upgrade_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'upgrade')
POSTGRES_PASS = os.getenv('POSTGRES_PASSWORD', '')


async def requeue_failed():
    conn = await asyncpg.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        database=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS
    )

    rows = await conn.fetch("""
        SELECT pr.pipeline_id, pr.sample_id, s.sample_code
        FROM pipeline_runs pr
        JOIN samples s ON s.sample_id = pr.sample_id
        WHERE pr.status = 'failed'
        ORDER BY pr.pipeline_id
    """)

    logger.info(f"Found {len(rows)} failed pipelines to re-queue")

    from tasks.pipeline_tasks import enqueue_pipeline

    success = 0
    skipped = 0
    errors = 0

    for row in rows:
        pipeline_id = row['pipeline_id']
        sample_id   = row['sample_id']
        sample_code = row['sample_code']
        bronze_path = f"genomic-bronze/{sample_code}/raw/"

        try:
            # Reset pipeline status to pending
            await conn.execute("""
                UPDATE pipeline_runs
                SET status = 'pending',
                    error_message = NULL,
                    job_id = NULL,
                    completed_at = NULL,
                    updated_at = NOW()
                WHERE pipeline_id = $1
            """, pipeline_id)

            # Enqueue RQ job
            job = enqueue_pipeline(
                pipeline_id=pipeline_id,
                sample_code=sample_code,
                input_dir=bronze_path,
                output_dir=f"/results/{sample_code}",
                params={}
            )

            # Save job_id
            await conn.execute("""
                UPDATE pipeline_runs SET job_id = $1, status = 'queued', updated_at = NOW()
                WHERE pipeline_id = $2
            """, job.id, pipeline_id)

            success += 1
            logger.info(f"[{success}/{len(rows)}] Queued pipeline {pipeline_id} ({sample_code}) → job {job.id}")

        except Exception as e:
            errors += 1
            logger.error(f"Failed to re-queue pipeline {pipeline_id} ({sample_code}): {e}")

    await conn.close()
    logger.info(f"\nDone: {success} queued, {skipped} skipped, {errors} errors")


if __name__ == '__main__':
    asyncio.run(requeue_failed())

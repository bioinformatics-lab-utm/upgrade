#!/usr/bin/env python3
"""
Queue 100 samples for pipeline execution.
Picks failed pipeline runs that have files in MinIO Bronze,
resets them to pending and enqueues via RQ.
Run inside backend container:
  docker exec upgrade_web_backend python3 /app/scripts/batch/queue_100.py
"""
import asyncio
import sys
import os

sys.path.insert(0, '/app')
os.chdir('/app')

import asyncpg
from minio import Minio
from tasks.pipeline_tasks import enqueue_pipeline
from config import config

LIMIT = 100


async def main():
    minio = Minio(
        os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
        access_key=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        secret_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        secure=False,
    )

    dsn = (f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
           f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}")
    conn = await asyncpg.connect(dsn)

    try:
        # Get up to LIMIT failed pipeline runs that have Bronze files
        failed_runs = await conn.fetch("""
            SELECT pr.pipeline_id, pr.sample_id, s.sample_code
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE pr.status = 'failed'
            ORDER BY pr.pipeline_id
            LIMIT $1
        """, LIMIT * 3)  # fetch extra, filter by Bronze presence below

        print(f"Found {len(failed_runs)} failed runs to check")

        bucket_id = await conn.fetchval(
            "SELECT bucket_id FROM minio_buckets WHERE bucket_name = 'genomic-bronze'"
        )

        queued = 0
        skipped = 0

        for row in failed_runs:
            if queued >= LIMIT:
                break

            pipeline_id = row['pipeline_id']
            sample_id   = row['sample_id']
            sample_code = row['sample_code']

            # Check Bronze files exist
            try:
                objects = list(minio.list_objects('genomic-bronze', prefix=f"{sample_code}/", recursive=True))
                fastq_files = [o for o in objects if o.object_name.endswith(('.fastq.gz', '.fq.gz', '.fastq', '.fq'))]
            except Exception as e:
                print(f"  SKIP {sample_code}: MinIO error — {e}")
                skipped += 1
                continue

            if not fastq_files:
                print(f"  SKIP {sample_code}: no FASTQ in Bronze")
                skipped += 1
                continue

            # Reset pipeline status to pending
            await conn.execute("""
                UPDATE pipeline_runs
                SET status = 'pending',
                    error_message = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    job_id = NULL
                WHERE pipeline_id = $1
            """, pipeline_id)

            # Ensure minio_objects records exist for this pipeline
            existing = await conn.fetchval(
                "SELECT count(*) FROM minio_objects WHERE pipeline_id = $1 AND bucket_id = $2",
                pipeline_id, bucket_id
            )
            if not existing:
                for obj in fastq_files:
                    stat = minio.stat_object('genomic-bronze', obj.object_name)
                    await conn.execute("""
                        INSERT INTO minio_objects (
                            bucket_id, object_key, object_name, object_size_bytes,
                            content_type, etag, sample_id, pipeline_id, layer_stage
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'raw')
                        ON CONFLICT DO NOTHING
                    """,
                        bucket_id,
                        obj.object_name,
                        os.path.basename(obj.object_name),
                        stat.size,
                        'application/gzip',
                        stat.etag,
                        sample_id,
                        pipeline_id,
                    )

            # Enqueue
            results_path = f"/tmp/nextflow/{sample_code}/results"
            try:
                job = enqueue_pipeline(
                    pipeline_id=pipeline_id,
                    sample_code=sample_code,
                    input_dir=f"genomic-bronze/{sample_code}/raw/",
                    output_dir=results_path,
                    params={},
                )
                job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
                await conn.execute(
                    "UPDATE pipeline_runs SET status='queued', job_id=$1 WHERE pipeline_id=$2",
                    job_id, pipeline_id
                )
                queued += 1
                print(f"  [{queued:3d}] QUEUED {sample_code} (pipeline={pipeline_id}, job={job_id[:16]}...)")
            except Exception as e:
                print(f"  ERROR {sample_code}: {e}")
                skipped += 1

        print(f"\nDone: {queued} queued, {skipped} skipped")

        # Status summary
        stats = await conn.fetchrow("""
            SELECT
              count(*) FILTER (WHERE status='queued')    as queued,
              count(*) FILTER (WHERE status='running')   as running,
              count(*) FILTER (WHERE status='pending')   as pending,
              count(*) FILTER (WHERE status='completed') as completed,
              count(*) FILTER (WHERE status='failed')    as failed
            FROM pipeline_runs
        """)
        print(f"\nDB state: queued={stats['queued']} running={stats['running']} "
              f"pending={stats['pending']} completed={stats['completed']} failed={stats['failed']}")

    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

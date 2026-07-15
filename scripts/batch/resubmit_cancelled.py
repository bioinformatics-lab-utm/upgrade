#!/usr/bin/env python3
"""
Re-queue cancelled pipeline runs whose FASTQ files are already in MinIO bronze.
Bypasses presigned-upload (rejects existing samples) by inserting directly into DB,
registering files in minio_objects, and enqueuing to Redis/RQ.
"""

import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import redis
from minio import Minio
from rq import Queue

DB_DSN = os.environ.get(
    "DB_DSN",
    "postgresql://upgrade:58m1-aS96SEVDLA-CRXM7XBrRpN7bA0f@127.0.0.1:5433/upgrade_db"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://:redis123@localhost:6379/0")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_USER = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_PASS = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin_password")
BRONZE_BUCKET = "genomic-bronze"
BRONZE_BUCKET_ID = 1  # from minio_buckets table
RQ_QUEUE = "pipeline-queue"
DELAY = 30


def find_fastq_in_minio(minio_client: Minio, sample_name: str) -> tuple[str, str, int, str]:
    """Returns (object_key, filename, size_bytes, etag)."""
    for obj in minio_client.list_objects(BRONZE_BUCKET, prefix=f"{sample_name}/", recursive=True):
        if obj.object_name.endswith(".fastq.gz"):
            stat = minio_client.stat_object(BRONZE_BUCKET, obj.object_name)
            etag = stat.etag or ""
            return obj.object_name, os.path.basename(obj.object_name), stat.size, etag
    raise FileNotFoundError(f"No .fastq.gz under {BRONZE_BUCKET}/{sample_name}/")


def requeue_sample(conn, q, minio_client: Minio,
                   sample_name: str, sample_id: int,
                   bronze_path: str, silver_path: str) -> bool:
    now = datetime.now(timezone.utc)
    results_path = f"/results/{sample_name}"
    silver_path = silver_path or f"genomic-silver/{sample_name}/"

    # Find actual FASTQ in MinIO
    object_key, filename, size_bytes, etag = find_fastq_in_minio(minio_client, sample_name)
    print(f"  [MINIO] {filename} ({size_bytes/1024/1024:.1f} MB) → {object_key}")

    with conn.cursor() as cur:
        # Create new pipeline_run
        cur.execute("""
            INSERT INTO pipeline_runs (
                sample_id, sample_name, pipeline_name, status,
                bronze_path, silver_path, results_path,
                created_at, updated_at, queued_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING pipeline_id
        """, (
            sample_id, sample_name, "nextflow_pipeline", "queued",
            bronze_path, silver_path, results_path,
            now, now, now,
        ))
        pipeline_id = cur.fetchone()[0]

        job_id = f"job_{pipeline_id}_{now.strftime('%Y%m%d_%H%M%S')}"
        cur.execute("UPDATE pipeline_runs SET job_id=%s WHERE pipeline_id=%s",
                    (job_id, pipeline_id))

        # Register file in minio_objects (required by download_from_bronze)
        cur.execute("""
            INSERT INTO minio_objects (
                bucket_id, object_key, object_name, object_size_bytes,
                content_type, etag, sample_id, pipeline_id, layer_stage
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'raw')
        """, (
            BRONZE_BUCKET_ID, object_key, filename, size_bytes,
            "application/gzip", etag, sample_id, pipeline_id,
        ))
        conn.commit()

    # Enqueue to RQ
    job = q.enqueue(
        "tasks.pipeline_tasks.run_nextflow_pipeline",
        pipeline_id=pipeline_id,
        sample_code=sample_name,
        input_dir=bronze_path,
        output_dir=results_path,
        params={},
        job_id=job_id,
        job_timeout=86400,
        result_ttl=86400,
        failure_ttl=86400,
    )

    actual_id = job.id.decode() if isinstance(job.id, bytes) else job.id
    print(f"  [OK] pipeline_id={pipeline_id}, job_id={actual_id}")
    return True


def main():
    samples = [line.strip() for line in sys.stdin if line.strip()]
    print(f"Re-queuing {len(samples)} samples")

    conn = psycopg2.connect(DB_DSN)
    redis_conn = redis.from_url(REDIS_URL)
    q = Queue(RQ_QUEUE, connection=redis_conn)
    minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)

    # Fetch sample_id + paths from latest cancelled run per sample
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (sample_name)
              sample_id, sample_name, bronze_path, silver_path
            FROM pipeline_runs
            WHERE status='cancelled' AND sample_name = ANY(%s)
            ORDER BY sample_name, pipeline_id DESC
        """, (samples,))
        rows = {r["sample_name"]: r for r in cur.fetchall()}

    submitted, failed = 0, 0
    for i, sample in enumerate(samples):
        print(f"\n[SAMPLE] {sample}")
        if sample not in rows:
            print(f"  [SKIP] Not found in cancelled runs")
            failed += 1
            continue

        row = rows[sample]
        try:
            requeue_sample(
                conn, q, minio_client,
                sample_name=row["sample_name"],
                sample_id=row["sample_id"],
                bronze_path=row["bronze_path"],
                silver_path=row["silver_path"],
            )
            submitted += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            conn.rollback()
            failed += 1

        if i < len(samples) - 1:
            print(f"  [WAIT] {DELAY}s...")
            time.sleep(DELAY)

    conn.close()
    print(f"\n[DONE] Submitted: {submitted}, Failed: {failed}")


if __name__ == "__main__":
    main()

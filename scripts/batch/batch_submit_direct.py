#!/usr/bin/env python3
"""
Batch-submit samples directly to the pipeline, bypassing the presigned-upload API
(which rejects samples that already exist in the samples table).

For each sample:
  1. Find FASTQ on disk (searches SRA_DIRS in order)
  2. Get or create sample record in DB
  3. Upload FASTQ to MinIO bronze (skip if already there)
  4. Create pipeline_run + minio_objects entry
  5. Enqueue to Redis/RQ

Usage:
  cat sample_list.txt | python3 batch_submit_direct.py [--delay 30] [--dry-run]
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path

import psycopg2
import psycopg2.extras
import redis
from minio import Minio
from minio.error import S3Error
from rq import Queue

# ── config ──────────────────────────────────────────────────────────────────
SRA_DIRS = [
    Path("/home/nicolaedrabcinski/upgrade/ont_sra_500"),
    Path("/home/nicolaedrabcinski/upgrade/ont_sra_50"),
    Path("/data/large_samples"),
]
DB_DSN = os.environ.get(
    "DB_DSN",
    "postgresql://upgrade:58m1-aS96SEVDLA-CRXM7XBrRpN7bA0f@127.0.0.1:5433/upgrade_db"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://:redis123@localhost:6379/0")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_USER = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_PASS = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin_password")
BRONZE_BUCKET = "genomic-bronze"
BRONZE_BUCKET_ID = 1
RQ_QUEUE = "pipeline-queue"
COLLECTION_DATE = "2025-02-27"
DEFAULT_DELAY = 30


def find_fastq(sample: str) -> Path | None:
    for d in SRA_DIRS:
        p = d / sample / f"{sample}.fastq.gz"
        if p.exists():
            return p
        # some dirs have sub-run suffixes like sample_1.fastq.gz
        candidates = list((d / sample).glob("*.fastq.gz")) if (d / sample).exists() else []
        if candidates:
            return candidates[0]
    return None


def get_or_create_sample(conn, sample_code: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT sample_id FROM samples WHERE sample_code = %s", (sample_code,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("""
            INSERT INTO samples (sample_code, sample_type, collection_date, created_at)
            VALUES (%s, 'nanopore', %s, NOW())
            RETURNING sample_id
        """, (sample_code, date.fromisoformat(COLLECTION_DATE)))
        sid = cur.fetchone()[0]
        conn.commit()
        return sid


def file_in_minio(minio_client: Minio, object_key: str) -> tuple[bool, int, str]:
    """Returns (exists, size, etag)."""
    try:
        stat = minio_client.stat_object(BRONZE_BUCKET, object_key)
        return True, stat.size, stat.etag or ""
    except S3Error:
        return False, 0, ""


def upload_to_minio(minio_client: Minio, local_path: Path, object_key: str) -> tuple[int, str]:
    minio_client.fput_object(BRONZE_BUCKET, object_key, str(local_path),
                             content_type="application/gzip")
    stat = minio_client.stat_object(BRONZE_BUCKET, object_key)
    return stat.size, stat.etag or ""


def submit_sample(conn, q, minio_client: Minio, sample_name: str, dry_run: bool) -> bool:
    fastq = find_fastq(sample_name)
    if not fastq:
        print(f"  [SKIP] No FASTQ found on disk")
        return False

    size_mb = fastq.stat().st_size / 1024 / 1024
    print(f"  [FILE] {fastq.name} ({size_mb:.1f} MB)")

    if dry_run:
        print(f"  [DRY-RUN] Would upload and submit")
        return True

    sample_id = get_or_create_sample(conn, sample_name)
    print(f"  [DB] sample_id={sample_id}")

    # Upload to MinIO (skip if already present)
    object_key = f"{sample_name}/raw/{fastq.name}"
    exists, size_bytes, etag = file_in_minio(minio_client, object_key)

    if exists:
        print(f"  [MINIO] Already in bronze ({size_bytes/1024/1024:.1f} MB), skipping upload")
    else:
        print(f"  [MINIO] Uploading → {BRONZE_BUCKET}/{object_key}")
        t0 = time.time()
        try:
            size_bytes, etag = upload_to_minio(minio_client, fastq, object_key)
        except S3Error as e:
            print(f"  [ERROR] MinIO upload failed: {e}")
            return False
        elapsed = time.time() - t0
        print(f"  [MINIO] Done in {elapsed:.0f}s ({size_bytes/1024/1024/max(elapsed,0.1):.0f} MB/s)")

    # Create pipeline_run + minio_objects + enqueue
    now = datetime.now(timezone.utc)
    bronze_path = f"{BRONZE_BUCKET}/{sample_name}/raw/"
    silver_path = f"genomic-silver/{sample_name}/"
    results_path = f"/results/{sample_name}"
    job_id_base = now.strftime("%Y%m%d_%H%M%S")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_runs (
                sample_id, sample_name, pipeline_name, status,
                bronze_path, silver_path, results_path,
                created_at, updated_at, queued_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING pipeline_id
        """, (sample_id, sample_name, "nextflow_pipeline", "queued",
              bronze_path, silver_path, results_path, now, now, now))
        pipeline_id = cur.fetchone()[0]

        job_id = f"job_{pipeline_id}_{job_id_base}"
        cur.execute("UPDATE pipeline_runs SET job_id=%s WHERE pipeline_id=%s",
                    (job_id, pipeline_id))

        cur.execute("""
            INSERT INTO minio_objects (
                bucket_id, object_key, object_name, object_size_bytes,
                content_type, etag, sample_id, pipeline_id, layer_stage
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'raw')
        """, (BRONZE_BUCKET_ID, object_key, fastq.name, size_bytes,
              "application/gzip", etag, sample_id, pipeline_id))
        conn.commit()

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
    print(f"  [OK] pipeline_id={pipeline_id}, job={actual_id}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    samples = [ln.strip() for ln in sys.stdin if ln.strip()]
    print(f"Submitting {len(samples)} samples (delay={args.delay}s, dry_run={args.dry_run})")

    if args.dry_run:
        conn, q, mc = None, None, None
    else:
        conn = psycopg2.connect(DB_DSN)
        redis_conn = redis.from_url(REDIS_URL)
        q = Queue(RQ_QUEUE, connection=redis_conn)
        mc = Minio(MINIO_ENDPOINT, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)
        if not mc.bucket_exists(BRONZE_BUCKET):
            mc.make_bucket(BRONZE_BUCKET)

    submitted = failed = 0
    for i, sample in enumerate(samples):
        print(f"\n[{i+1}/{len(samples)}] {sample}")
        try:
            ok = submit_sample(conn, q, mc, sample, args.dry_run)
        except Exception as e:
            print(f"  [ERROR] {e}")
            if conn:
                conn.rollback()
            ok = False

        if ok:
            submitted += 1
        else:
            failed += 1

        if not args.dry_run and i < len(samples) - 1:
            time.sleep(args.delay)

    if conn:
        conn.close()
    print(f"\n[DONE] Submitted: {submitted}, Failed: {failed}")


if __name__ == "__main__":
    main()

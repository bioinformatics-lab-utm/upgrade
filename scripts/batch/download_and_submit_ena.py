#!/usr/bin/env python3
"""
Download ONT metagenomics samples from ENA and submit to UPGRADE pipeline.
For each accession:
  1. Query ENA Portal API for FASTQ FTP URL + size
  2. Download with curl (resume-capable)
  3. Upload to MinIO bronze
  4. Create pipeline_run + minio_objects
  5. Enqueue to Redis/RQ
  6. Delete local file after upload

Usage:
  cat accessions.txt | python3 download_and_submit_ena.py [--delay 5] [--dry-run]
  cat accessions.txt | python3 download_and_submit_ena.py --jobs 2  # parallel downloads
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, date
from pathlib import Path

import psycopg2
import psycopg2.extras
import redis
from minio import Minio
from minio.error import S3Error
from rq import Queue

# ── config ─────────────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path("/data/env_metagenomes")
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
DELETE_AFTER_UPLOAD = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── ENA API ─────────────────────────────────────────────────────────────────
def query_ena(accession: str) -> dict | None:
    url = (
        "https://www.ebi.ac.uk/ena/portal/api/filereport"
        f"?accession={accession}"
        "&result=read_run"
        "&fields=run_accession,fastq_ftp,fastq_bytes,instrument_platform,library_source"
        "&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data:
            return None
        row = data[0]
        ftps = [f.strip() for f in row.get("fastq_ftp", "").split(";") if f.strip()]
        sizes = [int(s) for s in row.get("fastq_bytes", "").split(";") if s.strip().isdigit()]
        if not ftps or not sizes:
            return None
        # Take largest file (ONT = single FASTQ; if split, take the biggest)
        pairs = sorted(zip(sizes, ftps), reverse=True)
        best_size, best_ftp = pairs[0]
        return {
            "accession": accession,
            "ftp_url": "ftp://" + best_ftp,
            "size_bytes": best_size,
            "platform": row.get("instrument_platform", ""),
        }
    except Exception as e:
        log.warning(f"[ENA] {accession}: query failed: {e}")
        return None


# ── DB helpers ──────────────────────────────────────────────────────────────
def get_or_create_sample(conn, sample_code: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT sample_id FROM samples WHERE sample_code = %s", (sample_code,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("""
            INSERT INTO samples (sample_code, sample_type, collection_date, created_at)
            VALUES (%s, 'nanopore', %s, NOW()) RETURNING sample_id
        """, (sample_code, date.fromisoformat(COLLECTION_DATE)))
        sid = cur.fetchone()[0]
        conn.commit()
        return sid


def create_pipeline_run(conn, q, minio_client: Minio,
                        sample_name: str, sample_id: int,
                        object_key: str, filename: str,
                        size_bytes: int, etag: str) -> str:
    now = datetime.now(timezone.utc)
    bronze_path = f"{BRONZE_BUCKET}/{sample_name}/raw/"
    silver_path = f"genomic-silver/{sample_name}/"
    results_path = f"/results/{sample_name}"

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

        job_id = f"job_{pipeline_id}_{now.strftime('%Y%m%d_%H%M%S')}"
        cur.execute("UPDATE pipeline_runs SET job_id=%s WHERE pipeline_id=%s",
                    (job_id, pipeline_id))

        cur.execute("""
            INSERT INTO minio_objects (
                bucket_id, object_key, object_name, object_size_bytes,
                content_type, etag, sample_id, pipeline_id, layer_stage
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'raw')
        """, (BRONZE_BUCKET_ID, object_key, filename, size_bytes,
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
    log.info(f"  [OK] pipeline_id={pipeline_id}, job={actual_id}")
    return actual_id


# ── download ─────────────────────────────────────────────────────────────────
def download_fastq(ftp_url: str, dest: Path) -> bool:
    """Download with curl, resume if partial."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl", "-C", "-", "-L", "--retry", "3", "--retry-delay", "10",
        "--connect-timeout", "30", "--max-time", "7200",
        "-o", str(dest), ftp_url,
    ]
    log.info(f"  [DL] {ftp_url} → {dest}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        log.error(f"  [DL] curl failed (exit {result.returncode})")
        return False
    if not dest.exists() or dest.stat().st_size < 1000:
        log.error(f"  [DL] File too small after download")
        return False
    return True


# ── MinIO ────────────────────────────────────────────────────────────────────
def file_in_minio(mc: Minio, key: str) -> tuple[bool, int, str]:
    try:
        st = mc.stat_object(BRONZE_BUCKET, key)
        return True, st.size, st.etag or ""
    except S3Error:
        return False, 0, ""


def upload_to_minio(mc: Minio, local: Path, key: str) -> tuple[int, str]:
    mc.fput_object(BRONZE_BUCKET, key, str(local), content_type="application/gzip")
    st = mc.stat_object(BRONZE_BUCKET, key)
    return st.size, st.etag or ""


# ── main loop ────────────────────────────────────────────────────────────────
def process_accession(conn, q, mc: Minio, accession: str, dry_run: bool) -> bool:
    log.info(f"\n[ACC] {accession}")

    # Query ENA
    info = query_ena(accession)
    if not info:
        log.warning(f"  [SKIP] ENA query returned nothing")
        return False

    size_gb = info["size_bytes"] / 1e9
    log.info(f"  [ENA] {info['ftp_url']} ({size_gb:.2f} GB)")

    if dry_run:
        log.info(f"  [DRY-RUN] Would download {size_gb:.2f} GB and submit")
        return True

    filename = info["ftp_url"].split("/")[-1]
    if not filename.endswith(".fastq.gz"):
        filename = f"{accession}.fastq.gz"

    object_key = f"{accession}/raw/{filename}"

    # Check MinIO first (skip download if already there)
    exists, size_bytes, etag = file_in_minio(mc, object_key)
    if exists:
        log.info(f"  [MINIO] Already in bronze ({size_bytes/1e9:.2f} GB), skipping download")
    else:
        # Download
        local_path = DOWNLOAD_DIR / accession / filename
        ok = download_fastq(info["ftp_url"], local_path)
        if not ok:
            return False

        # Upload to MinIO
        log.info(f"  [MINIO] Uploading → {BRONZE_BUCKET}/{object_key}")
        t0 = time.time()
        try:
            size_bytes, etag = upload_to_minio(mc, local_path, object_key)
        except S3Error as e:
            log.error(f"  [MINIO] Upload failed: {e}")
            return False
        elapsed = time.time() - t0
        speed = size_bytes / 1e6 / max(elapsed, 0.1)
        log.info(f"  [MINIO] Done in {elapsed:.0f}s ({speed:.0f} MB/s)")

        # Delete local file
        if DELETE_AFTER_UPLOAD:
            local_path.unlink(missing_ok=True)
            log.info(f"  [CLEANUP] Deleted local file")

    # DB + enqueue
    sample_id = get_or_create_sample(conn, accession)
    log.info(f"  [DB] sample_id={sample_id}")

    create_pipeline_run(conn, q, mc, accession, sample_id, object_key, filename,
                        size_bytes, etag)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=int, default=5,
                        help="Seconds between pipeline submissions (default 5 — pipeline runs async)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    accessions = [ln.strip() for ln in sys.stdin if ln.strip()]
    log.info(f"Processing {len(accessions)} accessions (delay={args.delay}s, dry_run={args.dry_run})")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        conn = q = mc = None
    else:
        conn = psycopg2.connect(DB_DSN)
        redis_conn = redis.from_url(REDIS_URL)
        q = Queue(RQ_QUEUE, connection=redis_conn)
        mc = Minio(MINIO_ENDPOINT, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)

    submitted = failed = 0
    for i, acc in enumerate(accessions):
        try:
            ok = process_accession(conn, q, mc, acc, args.dry_run)
        except Exception as e:
            log.error(f"  [ERROR] {acc}: {e}", exc_info=True)
            if conn:
                conn.rollback()
            ok = False

        if ok:
            submitted += 1
        else:
            failed += 1

        if not args.dry_run and i < len(accessions) - 1:
            time.sleep(args.delay)

    if conn:
        conn.close()
    log.info(f"\n[DONE] Submitted: {submitted}, Failed: {failed}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Batch-submit SRA samples to the UPGRADE pipeline.

Flow per sample:
  1. POST /api/auth/login  → JWT token
  2. POST /api/pipeline/presigned-upload  → sample_id, pipeline_id, upload_urls
  3. Upload .fastq.gz directly to MinIO via minio-py client (no HTTP round-trip)
  4. POST /api/pipeline/confirm-upload  → enqueues RQ job

Usage:
  python3 batch_submit_sra.py --count 20 [--dry-run]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from minio import Minio
from minio.error import S3Error

SRA_DIR = Path("/home/nicolaedrabcinski/upgrade/ont_sra_50")
API_BASE = "http://localhost:8000"
MINIO_ENDPOINT = "localhost:9000"
MINIO_BUCKET = "genomic-bronze"

USERNAME = "nicolaedrabcinski"
PASSWORD = os.environ.get("UPGRADE_USER_PASSWORD", "g30FpPhyUVOHuFoP3lLLR5CChYo")
MINIO_USER = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_PASS = os.environ.get("MINIO_ROOT_PASSWORD", "UFYf66XRd-Dwo2qzXNajBzishrLWiPHd")

CONCURRENCY_DELAY = 30  # seconds between job submissions to avoid overwhelming RQ


def get_jwt() -> str:
    resp = requests.post(f"{API_BASE}/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    resp.raise_for_status()
    token = resp.json().get("token") or resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"No token in login response: {resp.json()}")
    print(f"[AUTH] Logged in as {USERNAME}")
    return token


def presigned_upload(token: str, sample_code: str, filename: str, file_size: int) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "sample_code": sample_code,
        "sample_type": "nanopore",
        "collection_date": "2025-02-27",
        "pipeline_name": "nextflow_pipeline",
        "files": [
            {
                "filename": filename,
                "size": file_size,
                "content_type": "application/gzip",
            }
        ],
        "parameters": {},
        "notes": f"SRA batch import: {sample_code}",
    }
    resp = requests.post(f"{API_BASE}/api/pipeline/presigned-upload", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def upload_to_minio(local_path: Path, minio_object_key: str, file_size: int) -> None:
    client = Minio(MINIO_ENDPOINT, access_key=MINIO_USER, secret_key=MINIO_PASS, secure=False)

    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    client.fput_object(
        MINIO_BUCKET,
        minio_object_key,
        str(local_path),
        content_type="application/gzip",
    )


def confirm_upload(token: str, pipeline_id: int, sample_id: int, sample_code: str,
                   filename: str, file_size: int) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "pipeline_id": pipeline_id,
        "sample_id": sample_id,
        "sample_code": sample_code,
        "uploaded_files": [
            {
                "filename": filename,
                "size": file_size,
                "object_path": object_path,
            }
        ],
        "parameters": {},
    }
    resp = requests.post(f"{API_BASE}/api/pipeline/confirm-upload", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def submit_sample(token: str, sample_dir: Path, dry_run: bool) -> bool:
    sample_code = sample_dir.name
    fastq_files = list(sample_dir.glob("*.fastq.gz"))
    if not fastq_files:
        print(f"  [SKIP] {sample_code}: no .fastq.gz file found")
        return False

    fastq = fastq_files[0]
    file_size = fastq.stat().st_size
    size_mb = file_size / 1024 / 1024

    print(f"\n[SAMPLE] {sample_code} ({size_mb:.0f} MB)")

    if dry_run:
        print(f"  [DRY-RUN] Would upload {fastq.name} and submit pipeline")
        return True

    # Step 1: register in DB, get pipeline_id / sample_id
    try:
        presigned = presigned_upload(token, sample_code, fastq.name, file_size)
    except requests.HTTPError as e:
        print(f"  [ERROR] presigned-upload failed: {e.response.text}")
        return False

    pipeline_id = presigned["pipeline_id"]
    sample_id = presigned["sample_id"]
    # The upload_urls contain the minio object key
    upload_info = presigned.get("upload_urls", [{}])[0]
    object_path = upload_info.get("object_path") or f"{sample_code}/raw/{fastq.name}"
    print(f"  [DB] pipeline_id={pipeline_id}, sample_id={sample_id}")

    # Step 2: upload to MinIO directly (much faster than HTTP presigned)
    print(f"  [MINIO] Uploading {fastq.name} → {MINIO_BUCKET}/{object_path}")
    t0 = time.time()
    try:
        upload_to_minio(fastq, object_path, file_size)
    except S3Error as e:
        print(f"  [ERROR] MinIO upload failed: {e}")
        return False
    elapsed = time.time() - t0
    speed = size_mb / elapsed if elapsed > 0 else 0
    print(f"  [MINIO] Upload done in {elapsed:.0f}s ({speed:.0f} MB/s)")

    # Step 3: confirm upload → enqueue pipeline job
    try:
        result = confirm_upload(token, pipeline_id, sample_id, sample_code, fastq.name, file_size)
    except requests.HTTPError as e:
        print(f"  [ERROR] confirm-upload failed: {e.response.text}")
        return False

    print(f"  [OK] Job queued: {result.get('job_id')}, status={result.get('status')}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20, help="Number of samples to submit")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without doing it")
    parser.add_argument("--delay", type=int, default=CONCURRENCY_DELAY,
                        help="Seconds to wait between submissions")
    parser.add_argument("--skip", type=int, default=0, help="Skip the first N samples")
    args = parser.parse_args()

    sample_dirs = sorted([d for d in SRA_DIR.iterdir() if d.is_dir()])
    if args.skip:
        sample_dirs = sample_dirs[args.skip:]
    sample_dirs = sample_dirs[: args.count]

    print(f"Submitting {len(sample_dirs)} samples (dry_run={args.dry_run})")

    if not args.dry_run:
        token = get_jwt()
    else:
        token = "dry-run-token"

    submitted = 0
    failed = 0
    for i, sample_dir in enumerate(sample_dirs):
        ok = submit_sample(token, sample_dir, args.dry_run)
        if ok:
            submitted += 1
        else:
            failed += 1

        # Delay between submissions (not after the last one)
        if not args.dry_run and i < len(sample_dirs) - 1:
            print(f"  [WAIT] {args.delay}s before next submission...")
            time.sleep(args.delay)

    print(f"\n[DONE] Submitted: {submitted}, Failed: {failed}")


if __name__ == "__main__":
    main()

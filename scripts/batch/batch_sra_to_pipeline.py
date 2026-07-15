#!/usr/bin/env python3
"""
Batch SRA-to-Pipeline Script
Converts .sra files to .fastq.gz, uploads directly to MinIO,
and triggers pipeline execution via API for each sample.

Usage:
    python3 scripts/batch/batch_sra_to_pipeline.py
    python3 scripts/batch/batch_sra_to_pipeline.py --dry-run
    python3 scripts/batch/batch_sra_to_pipeline.py --sample SRR37301096
    python3 scripts/batch/batch_sra_to_pipeline.py --skip-conversion
    python3 scripts/batch/batch_sra_to_pipeline.py --convert-only
"""

import os
import sys
import json
import time
import subprocess
import requests
import argparse
import logging
from pathlib import Path
from datetime import datetime
from minio import Minio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/batch_sra_pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration (all credentials from environment) ---
API_BASE = os.getenv('API_URL', 'http://localhost:8000')
SRA_DIR = Path(os.getenv('SRA_DIR', './ont_sra_50'))
USERNAME = os.getenv('UPGRADE_USERNAME', '')
PASSWORD = os.getenv('UPGRADE_PASSWORD', '')
SAMPLE_TYPE = 'nanopore'
PIPELINE_NAME = 'nextflow_pipeline'
FASTERQ_THREADS = 8
WAIT_BETWEEN = 3  # seconds between submissions

if not USERNAME or not PASSWORD:
    logger.error("UPGRADE_USERNAME and UPGRADE_PASSWORD environment variables are required")
    sys.exit(1)

# MinIO direct access (same machine, bypass presigned URL issues)
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', '')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', '')

if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    logger.error("MINIO_ROOT_USER and MINIO_ROOT_PASSWORD environment variables are required")
    sys.exit(1)
MINIO_BUCKET = 'genomic-bronze'


def get_minio_client():
    """Create MinIO client for direct upload."""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def login(session):
    """Authenticate and return JWT token."""
    resp = session.post(f'{API_BASE}/api/auth/login', json={
        'username': USERNAME,
        'password': PASSWORD,
    })
    resp.raise_for_status()
    data = resp.json()
    if not data.get('success'):
        raise RuntimeError(f"Login failed: {data}")
    token = data['token']
    session.headers['Authorization'] = f'Bearer {token}'
    logger.info(f"Logged in as {USERNAME} (user_id={data['user']['user_id']})")
    return token


def find_sra_samples():
    """Find all SRA sample directories."""
    samples = []
    for d in sorted(SRA_DIR.iterdir()):
        if not d.is_dir():
            continue
        sra_file = d / f'{d.name}.sra'
        if sra_file.exists():
            samples.append({
                'sample_code': d.name,
                'sra_path': sra_file,
                'dir': d,
                'sra_size_mb': sra_file.stat().st_size / (1024 * 1024),
            })
    return samples


def convert_sra_to_fastq(sample, skip_if_exists=True):
    """Convert .sra to .fastq.gz using fasterq-dump + pigz."""
    sample_code = sample['sample_code']
    sample_dir = sample['dir']

    # Check if already converted
    fastq_gz = sample_dir / f'{sample_code}.fastq.gz'
    if skip_if_exists and fastq_gz.exists() and fastq_gz.stat().st_size > 0:
        logger.info(f"  FASTQ.GZ already exists: {fastq_gz.name} ({fastq_gz.stat().st_size / 1024 / 1024:.1f} MB)")
        return fastq_gz

    fastq_file = sample_dir / f'{sample_code}.fastq'

    # Step 1: fasterq-dump (SRA -> FASTQ)
    if not fastq_file.exists() or fastq_file.stat().st_size == 0:
        logger.info(f"  Converting SRA -> FASTQ with fasterq-dump...")
        cmd = [
            'fasterq-dump', str(sample['sra_path']),
            '--outdir', str(sample_dir),
            '--threads', str(FASTERQ_THREADS),
            '--force',
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            logger.error(f"  fasterq-dump failed: {result.stderr}")
            return None
        logger.info(f"  fasterq-dump done")

    # Find the output FASTQ file(s)
    fastq_files = list(sample_dir.glob(f'{sample_code}*.fastq'))
    if not fastq_files:
        logger.error(f"  No FASTQ files found after conversion")
        return None

    # Use the main file (ONT is single-end)
    main_fastq = fastq_file if fastq_file.exists() else fastq_files[0]

    # Step 2: Compress with pigz
    logger.info(f"  Compressing {main_fastq.name} with pigz...")
    result = subprocess.run(
        ['pigz', '-p', str(FASTERQ_THREADS), '-f', str(main_fastq)],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        logger.error(f"  pigz failed: {result.stderr}")
        return None

    fastq_gz = Path(str(main_fastq) + '.gz')
    if fastq_gz.exists():
        logger.info(f"  Compressed: {fastq_gz.name} ({fastq_gz.stat().st_size / 1024 / 1024:.1f} MB)")
        return fastq_gz

    logger.error(f"  Compressed file not found: {fastq_gz}")
    return None


def submit_sample(session, minio_client, sample_code, fastq_gz_path):
    """
    Upload to MinIO directly, then register via API:
    1. Upload file to MinIO (direct SDK, no presigned URL)
    2. Call presigned-upload to create sample + pipeline records
    3. Call confirm-upload to trigger pipeline
    """
    file_size = fastq_gz_path.stat().st_size
    filename = fastq_gz_path.name
    object_path = f"{sample_code}/raw/{filename}"

    # Step 1: Upload directly to MinIO
    logger.info(f"  Uploading {filename} ({file_size / 1024 / 1024:.1f} MB) to MinIO...")
    try:
        minio_client.fput_object(
            MINIO_BUCKET,
            object_path,
            str(fastq_gz_path),
            content_type='application/gzip',
        )
        logger.info(f"  Upload complete: {MINIO_BUCKET}/{object_path}")
    except Exception as e:
        logger.error(f"  MinIO upload failed: {e}")
        return None

    # Step 2: Register sample + pipeline via API
    logger.info(f"  Registering sample and pipeline via API...")
    resp = session.post(f'{API_BASE}/api/v2/pipeline/presigned-upload', json={
        'sample_code': sample_code,
        'sample_type': SAMPLE_TYPE,
        'collection_date': datetime.now().strftime('%Y-%m-%d'),
        'files': [{'name': filename, 'size': file_size}],
        'pipeline_name': PIPELINE_NAME,
        'parameters': {},
        'notes': f'ONT SRA batch import - {sample_code}',
    })

    if resp.status_code != 200:
        logger.error(f"  API register failed ({resp.status_code}): {resp.text}")
        return None

    presigned_data = resp.json()
    if not presigned_data.get('success'):
        logger.error(f"  API register error: {presigned_data}")
        return None

    sample_id = presigned_data['sample_id']
    pipeline_id = presigned_data['pipeline_id']
    logger.info(f"  Registered: sample_id={sample_id}, pipeline_id={pipeline_id}")

    # Step 3: Confirm upload and trigger pipeline
    logger.info(f"  Confirming upload and triggering pipeline...")
    resp = session.post(f'{API_BASE}/api/v2/pipeline/confirm-upload', json={
        'pipeline_id': pipeline_id,
        'sample_id': sample_id,
        'sample_code': sample_code,
        'uploaded_files': [{
            'filename': filename,
            'size': file_size,
            'object_path': object_path,
        }],
        'parameters': {},
    })

    if resp.status_code not in (200, 201):
        logger.error(f"  Confirm failed ({resp.status_code}): {resp.text}")
        return None

    confirm_data = resp.json()
    if not confirm_data.get('success'):
        logger.error(f"  Confirm error: {confirm_data}")
        return None

    job_id = confirm_data.get('job_id', 'unknown')
    logger.info(f"  Pipeline queued: pipeline_id={pipeline_id}, job_id={job_id}")
    return {
        'pipeline_id': pipeline_id,
        'sample_id': sample_id,
        'job_id': job_id,
    }


def main():
    parser = argparse.ArgumentParser(description='Batch SRA to Pipeline submission')
    parser.add_argument('--dry-run', action='store_true', help='List samples without processing')
    parser.add_argument('--sample', type=str, help='Process single sample by SRR code')
    parser.add_argument('--skip-conversion', action='store_true', help='Skip SRA conversion, use existing FASTQ.GZ')
    parser.add_argument('--convert-only', action='store_true', help='Only convert SRA to FASTQ.GZ, do not submit')
    parser.add_argument('--min-size-mb', type=float, default=0.1, help='Skip samples smaller than this (MB)')
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("  BATCH SRA -> PIPELINE SUBMISSION")
    logger.info("=" * 70)

    # Find samples
    samples = find_sra_samples()
    logger.info(f"Found {len(samples)} SRA samples in {SRA_DIR}")

    # Filter single sample
    if args.sample:
        samples = [s for s in samples if s['sample_code'] == args.sample]
        if not samples:
            logger.error(f"Sample {args.sample} not found")
            return

    # Filter by min size
    small_skipped = [s for s in samples if s['sra_size_mb'] < args.min_size_mb]
    samples = [s for s in samples if s['sra_size_mb'] >= args.min_size_mb]
    if small_skipped:
        logger.info(f"Skipping {len(small_skipped)} samples smaller than {args.min_size_mb} MB")

    if args.dry_run:
        logger.info(f"\n{'Sample':<20} {'SRA Size (MB)':>15}")
        logger.info("-" * 40)
        total_mb = 0
        for s in samples:
            logger.info(f"{s['sample_code']:<20} {s['sra_size_mb']:>12.1f} MB")
            total_mb += s['sra_size_mb']
        logger.info("-" * 40)
        logger.info(f"{'TOTAL':<20} {total_mb:>12.1f} MB ({len(samples)} samples)")
        return

    # Login to API
    session = requests.Session()
    session.headers['Content-Type'] = 'application/json'

    minio_client = None
    if not args.convert_only:
        login(session)
        minio_client = get_minio_client()
        # Verify MinIO connection
        buckets = [b.name for b in minio_client.list_buckets()]
        logger.info(f"MinIO connected. Buckets: {buckets}")
        if MINIO_BUCKET not in buckets:
            logger.error(f"Bucket '{MINIO_BUCKET}' not found!")
            return

    # Process
    stats = {'total': len(samples), 'converted': 0, 'submitted': 0, 'failed': 0, 'skipped': 0}

    for idx, sample in enumerate(samples, 1):
        sc = sample['sample_code']
        logger.info(f"\n[{idx}/{len(samples)}] {sc} ({sample['sra_size_mb']:.1f} MB SRA)")

        # Convert SRA -> FASTQ.GZ
        if args.skip_conversion:
            fastq_gz = sample['dir'] / f'{sc}.fastq.gz'
            if not fastq_gz.exists():
                logger.error(f"  FASTQ.GZ not found: {fastq_gz}")
                stats['failed'] += 1
                continue
        else:
            fastq_gz = convert_sra_to_fastq(sample)
            if not fastq_gz:
                logger.error(f"  Conversion failed for {sc}")
                stats['failed'] += 1
                continue
            stats['converted'] += 1

        if args.convert_only:
            continue

        # Submit to API
        result = submit_sample(session, minio_client, sc, fastq_gz)
        if result:
            stats['submitted'] += 1
        else:
            stats['failed'] += 1

        # Wait between submissions
        if idx < len(samples):
            time.sleep(WAIT_BETWEEN)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("  RESULTS")
    logger.info("=" * 70)
    logger.info(f"  Total samples:  {stats['total']}")
    logger.info(f"  Converted:      {stats['converted']}")
    logger.info(f"  Submitted:      {stats['submitted']}")
    logger.info(f"  Failed:         {stats['failed']}")
    logger.info(f"  Skipped:        {stats['skipped']}")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()

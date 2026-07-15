#!/usr/bin/env python3
"""
Top-500 Smallest SRA Samples -> Pipeline

Reads runinfo_full.csv, picks the top N smallest ONT metagenome samples
(with size_MB > 0), downloads via prefetch, converts to fastq.gz, uploads
to MinIO, and triggers the pipeline via API.

Usage:
    python3 scripts/batch/top500_to_pipeline.py --dry-run
    python3 scripts/batch/top500_to_pipeline.py
    python3 scripts/batch/top500_to_pipeline.py --limit 100 --max-size-mb 500
    python3 scripts/batch/top500_to_pipeline.py --skip-download --work-dir /data/sra
"""

import os
import sys
import csv
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
        logging.FileHandler('/tmp/top500_pipeline.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# --- Configuration ---
RUNINFO_CSV = Path(os.getenv('RUNINFO_CSV', './sra_ont_metagenomes/runinfo_full.csv'))
WORK_DIR    = Path(os.getenv('WORK_DIR', './sra_downloads'))
API_BASE    = os.getenv('API_URL', 'http://localhost:8000')
USERNAME    = os.getenv('UPGRADE_USERNAME', '')
PASSWORD    = os.getenv('UPGRADE_PASSWORD', '')
MINIO_ENDPOINT  = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS    = os.getenv('MINIO_ROOT_USER', '')
MINIO_SECRET    = os.getenv('MINIO_ROOT_PASSWORD', '')
MINIO_BUCKET    = 'genomic-bronze'
FASTERQ_THREADS = int(os.getenv('FASTERQ_THREADS', '8'))
WAIT_BETWEEN    = 3  # seconds between API submissions


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def load_top_n(csv_path: Path, limit: int, min_size_mb: float, max_size_mb: float) -> list[dict]:
    """Read runinfo_full.csv and return top-N smallest samples."""
    if not csv_path.exists():
        logger.error(f"CSV not found: {csv_path}")
        sys.exit(1)

    rows = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                size = float(row.get('size_MB') or 0)
            except ValueError:
                continue
            if size < min_size_mb or size > max_size_mb:
                continue
            rows.append({
                'run_id':   row['Run'],
                'size_mb':  size,
                'spots':    int(row.get('spots') or 0),
                'model':    row.get('Model', 'N/A'),
                'study':    row.get('SRAStudy', 'N/A'),
            })

    rows.sort(key=lambda r: r['size_mb'])
    selected = rows[:limit]
    logger.info(
        f"CSV: {len(rows)} eligible samples  →  selected top {len(selected)} smallest "
        f"(range: {selected[0]['size_mb']:.1f} – {selected[-1]['size_mb']:.1f} MB)"
        if selected else "No samples match filters"
    )
    return selected


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def already_have_fastq(sample_code: str, work_dir: Path) -> Path | None:
    """Return path to existing fastq.gz if present, else None."""
    candidates = [
        work_dir / sample_code / f'{sample_code}.fastq.gz',
        work_dir / sample_code / f'{sample_code}_1.fastq.gz',
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def download_sra(sample_code: str, work_dir: Path) -> Path | None:
    """Download .sra via prefetch into work_dir/sample_code/."""
    sample_dir = work_dir / sample_code
    sample_dir.mkdir(parents=True, exist_ok=True)

    sra_path = sample_dir / f'{sample_code}.sra'
    if sra_path.exists() and sra_path.stat().st_size > 0:
        logger.info(f"  SRA already present: {sra_path.name} ({sra_path.stat().st_size / 1e6:.1f} MB)")
        return sra_path

    logger.info(f"  Downloading {sample_code} via prefetch...")
    result = subprocess.run(
        ['prefetch', sample_code, '--output-directory', str(work_dir), '--max-size', '50G'],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0:
        logger.error(f"  prefetch failed: {result.stderr.strip()}")
        return None

    # prefetch can place the file at slightly different paths
    for candidate in [
        sra_path,
        work_dir / sample_code / f'{sample_code}' / f'{sample_code}.sra',
    ]:
        if candidate.exists():
            return candidate

    logger.error(f"  SRA file not found after prefetch")
    return None


def convert_to_fastq_gz(sample_code: str, sra_path: Path) -> Path | None:
    """Convert .sra -> fastq.gz using fasterq-dump + pigz."""
    sample_dir = sra_path.parent

    fastq_gz = sample_dir / f'{sample_code}.fastq.gz'
    if fastq_gz.exists() and fastq_gz.stat().st_size > 0:
        logger.info(f"  FASTQ.GZ already exists ({fastq_gz.stat().st_size / 1e6:.1f} MB)")
        return fastq_gz

    # fasterq-dump: SRA -> FASTQ
    logger.info(f"  Running fasterq-dump...")
    result = subprocess.run(
        ['fasterq-dump', str(sra_path), '--outdir', str(sample_dir),
         '--threads', str(FASTERQ_THREADS), '--force'],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0:
        logger.error(f"  fasterq-dump failed: {result.stderr.strip()}")
        return None

    # Find the output FASTQ (ONT is single-end)
    fastq_files = sorted(sample_dir.glob(f'{sample_code}*.fastq'))
    if not fastq_files:
        logger.error("  No FASTQ files found after fasterq-dump")
        return None

    main_fastq = next((f for f in fastq_files if f.name == f'{sample_code}.fastq'), fastq_files[0])

    # pigz compress
    logger.info(f"  Compressing {main_fastq.name} with pigz...")
    result = subprocess.run(
        ['pigz', '-p', str(FASTERQ_THREADS), '-f', str(main_fastq)],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0:
        logger.error(f"  pigz failed: {result.stderr.strip()}")
        return None

    out = Path(str(main_fastq) + '.gz')
    if out.exists():
        logger.info(f"  Compressed: {out.name} ({out.stat().st_size / 1e6:.1f} MB)")
        return out

    logger.error(f"  Compressed file missing: {out}")
    return None


# ---------------------------------------------------------------------------
# MinIO + API helpers
# ---------------------------------------------------------------------------

def get_minio_client() -> Minio:
    return Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)


def login(session: requests.Session) -> str:
    resp = session.post(f'{API_BASE}/api/auth/login', json={'username': USERNAME, 'password': PASSWORD})
    resp.raise_for_status()
    data = resp.json()
    if not data.get('success'):
        raise RuntimeError(f"Login failed: {data}")
    token = data['token']
    session.headers['Authorization'] = f'Bearer {token}'
    logger.info(f"Logged in as {USERNAME}")
    return token


def submit_sample(session: requests.Session, minio: Minio, sample_code: str, fastq_gz: Path) -> dict | None:
    """Upload to MinIO, register via API, confirm to trigger pipeline."""
    file_size = fastq_gz.stat().st_size
    filename  = fastq_gz.name
    obj_path  = f'{sample_code}/raw/{filename}'

    # 1. Upload to MinIO
    logger.info(f"  Uploading {filename} ({file_size / 1e6:.1f} MB) to MinIO...")
    try:
        minio.fput_object(MINIO_BUCKET, obj_path, str(fastq_gz), content_type='application/gzip')
        logger.info(f"  Uploaded: {MINIO_BUCKET}/{obj_path}")
    except Exception as e:
        logger.error(f"  MinIO upload failed: {e}")
        return None

    # 2. Register sample + pipeline
    resp = session.post(f'{API_BASE}/api/pipeline/presigned-upload', json={
        'sample_code':   sample_code,
        'sample_type':   'nanopore',
        'collection_date': datetime.now().strftime('%Y-%m-%d'),
        'files':         [{'name': filename, 'size': file_size}],
        'pipeline_name': 'nextflow_pipeline',
        'parameters':    {},
        'notes':         f'top500 batch import - {sample_code}',
    })
    if not resp.ok:
        body = resp.text[:200]
        if resp.status_code == 400 and 'already exists' in body:
            logger.warning(f"  Sample already registered: {body}")
            return 'already_exists'
        logger.error(f"  presigned-upload failed ({resp.status_code}): {body}")
        return None
    reg = resp.json()
    if not reg.get('success'):
        logger.error(f"  presigned-upload error: {reg}")
        return None
    sample_id  = reg['sample_id']
    pipeline_id = reg['pipeline_id']
    logger.info(f"  Registered: sample_id={sample_id}, pipeline_id={pipeline_id}")

    # 3. Confirm upload -> trigger pipeline
    resp = session.post(f'{API_BASE}/api/pipeline/confirm-upload', json={
        'pipeline_id':   pipeline_id,
        'sample_id':     sample_id,
        'sample_code':   sample_code,
        'uploaded_files': [{'filename': filename, 'size': file_size, 'object_path': obj_path}],
        'parameters':    {},
    })
    if resp.status_code not in (200, 201):
        logger.error(f"  confirm-upload failed ({resp.status_code}): {resp.text[:200]}")
        return None
    confirm = resp.json()
    if not confirm.get('success'):
        logger.error(f"  confirm-upload error: {confirm}")
        return None

    job_id = confirm.get('job_id', 'unknown')
    logger.info(f"  Pipeline queued: pipeline_id={pipeline_id}, job_id={job_id}")
    return {'pipeline_id': pipeline_id, 'sample_id': sample_id, 'job_id': job_id}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Submit top-N smallest ONT metagenome samples to pipeline')
    parser.add_argument('--csv',          default=str(RUNINFO_CSV), help='Path to runinfo_full.csv')
    parser.add_argument('--work-dir',     default=str(WORK_DIR),    help='Directory for downloaded files')
    parser.add_argument('--limit',        type=int, default=500,    help='Number of smallest samples to process (default: 500)')
    parser.add_argument('--min-size-mb',  type=float, default=0.5,  help='Minimum file size MB to include (default: 0.5)')
    parser.add_argument('--max-size-mb',  type=float, default=2000, help='Maximum file size MB to include (default: 2000)')
    parser.add_argument('--dry-run',      action='store_true',      help='Preview selected samples without processing')
    parser.add_argument('--skip-download',action='store_true',      help='Skip prefetch; expect fastq.gz already in work-dir')
    parser.add_argument('--convert-only', action='store_true',      help='Download and convert only, do not submit to API')
    parser.add_argument('--sample',       help='Process a single run ID only')
    args = parser.parse_args()

    work_dir = Path(args.work_dir)

    logger.info("=" * 70)
    logger.info("  TOP-500 SMALLEST ONT METAGENOMES -> PIPELINE")
    logger.info("=" * 70)

    # Load and filter samples
    samples = load_top_n(Path(args.csv), args.limit, args.min_size_mb, args.max_size_mb)
    if not samples:
        logger.error("No samples selected. Adjust filters.")
        sys.exit(1)

    if args.sample:
        samples = [s for s in samples if s['run_id'] == args.sample]
        if not samples:
            logger.error(f"Sample {args.sample} not found in selection")
            sys.exit(1)

    if args.dry_run:
        logger.info(f"\n{'Run ID':<16} {'Size MB':>10} {'Spots':>10}  Model")
        logger.info("-" * 60)
        for s in samples:
            logger.info(f"{s['run_id']:<16} {s['size_mb']:>10.1f} {s['spots']:>10,}  {s['model']}")
        total_mb = sum(s['size_mb'] for s in samples)
        logger.info("-" * 60)
        logger.info(f"{'TOTAL':<16} {total_mb:>10.1f} MB  ({len(samples)} samples)")
        return

    # Validate credentials
    if not args.convert_only:
        for var, name in [(USERNAME, 'UPGRADE_USERNAME'), (PASSWORD, 'UPGRADE_PASSWORD'),
                          (MINIO_ACCESS, 'MINIO_ROOT_USER'), (MINIO_SECRET, 'MINIO_ROOT_PASSWORD')]:
            if not var:
                logger.error(f"Environment variable {name} is required")
                sys.exit(1)

    # Setup clients
    session      = requests.Session()
    session.headers['Content-Type'] = 'application/json'
    minio_client = None

    if not args.convert_only:
        login(session)
        minio_client = get_minio_client()
        buckets = [b.name for b in minio_client.list_buckets()]
        logger.info(f"MinIO connected. Buckets: {buckets}")
        if MINIO_BUCKET not in buckets:
            logger.error(f"Bucket '{MINIO_BUCKET}' not found")
            sys.exit(1)

    # Process
    stats = {'total': len(samples), 'downloaded': 0, 'converted': 0, 'submitted': 0, 'failed': 0, 'skipped': 0}

    for idx, sample in enumerate(samples, 1):
        run_id = sample['run_id']
        logger.info(f"\n[{idx}/{len(samples)}] {run_id}  ({sample['size_mb']:.1f} MB, {sample['spots']:,} spots)")

        sample_dir = work_dir / run_id

        # Step 1: find or download fastq.gz
        fastq_gz = already_have_fastq(run_id, work_dir)

        if fastq_gz:
            logger.info(f"  FASTQ.GZ already present: {fastq_gz}")
        elif args.skip_download:
            logger.error(f"  --skip-download set but no fastq.gz found in {sample_dir}")
            stats['failed'] += 1
            continue
        else:
            # Download SRA
            sra_path = download_sra(run_id, work_dir)
            if not sra_path:
                stats['failed'] += 1
                continue
            stats['downloaded'] += 1

            # Convert
            fastq_gz = convert_to_fastq_gz(run_id, sra_path)
            if not fastq_gz:
                stats['failed'] += 1
                continue

        stats['converted'] += 1

        if args.convert_only:
            continue

        # Step 2: submit to API
        result = submit_sample(session, minio_client, run_id, fastq_gz)
        if result == 'already_exists':
            stats['skipped'] += 1
        elif result:
            stats['submitted'] += 1
        else:
            stats['failed'] += 1

        if idx < len(samples):
            time.sleep(WAIT_BETWEEN)

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("  RESULTS")
    logger.info("=" * 70)
    logger.info(f"  Total selected:  {stats['total']}")
    logger.info(f"  Downloaded:      {stats['downloaded']}")
    logger.info(f"  Converted:       {stats['converted']}")
    logger.info(f"  Submitted:       {stats['submitted']}")
    logger.info(f"  Failed:          {stats['failed']}")
    logger.info(f"  Skipped:         {stats['skipped']}")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Download ~100 environmental metagenomics ONT samples (1-2 GB each) from ENA/NCBI
and queue them through the pipeline.

Run inside the backend container:
  docker exec upgrade_web_backend python3 /app/scripts/batch/download_and_queue_env_metagenomes.py

Or on the host (needs MinIO + Postgres accessible):
  python3 scripts/batch/download_and_queue_env_metagenomes.py
"""
import asyncio
import os
import sys
import json
import subprocess
import logging
import time
import urllib.request
import shutil
from pathlib import Path
from datetime import date

sys.path.insert(0, '/app')
os.chdir('/app')

import asyncpg
from minio import Minio
from tasks.pipeline_tasks import enqueue_pipeline
from config import config

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DOWNLOAD_DIR = Path('/data/env_metagenomes')
BUCKET = 'genomic-bronze'

# Target: ~100 samples, 1-2 GB each (1.0 – 2.1 GB on disk)
MIN_BYTES = 1_000_000_000   # 1.0 GB
MAX_BYTES = 2_200_000_000   # 2.2 GB
TARGET_COUNT = 100

# Remove local file after successful MinIO upload (saves disk)
DELETE_AFTER_UPLOAD = True

# Seconds to wait between pipeline submissions (RQ processes one at a time)
WAIT_BETWEEN = 2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/download_queue_env.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate accessions (150 selected from ENA/NCBI search)
# Oxford Nanopore, WGS, METAGENOMIC, estimated 1-2 GB
# ---------------------------------------------------------------------------
CANDIDATES = [
    "ERR15816914", "ERR2529201", "ERR2675610", "ERR3200811", "ERR3212530",
    "ERR3765657", "ERR4777633", "ERR5363646", "ERR5261678", "ERR7757480",
    "ERR12018799", "ERR11513044", "ERR11725752", "ERR12075432", "ERR14747353",
    "ERR15093277", "SRR26512899", "SRR26624772", "SRR28162905", "SRR28820000",
    "SRR29483344", "SRR29660113", "SRR29757988", "SRR31928295", "SRR34680177",
    "SRR34982038", "SRR35672351", "SRR35699590", "SRR36682515", "SRR35779906",
    "SRR36873161", "SRR13777393", "SRR11797282", "SRR12390954", "SRR13748115",
    "SRR18100901", "SRR18969722", "SRR20746828", "SRR25444963", "ERR15817656",
    "ERR3212551", "ERR4777634", "ERR5261684", "ERR7764220", "ERR12018801",
    "ERR11513056", "ERR12075433", "ERR14747356", "ERR15093291", "SRR26512909",
    "SRR28820017", "SRR29483345", "SRR29660129", "SRR31928339", "SRR34680178",
    "SRR35699593", "SRR13777395", "SRR11797283", "SRR12390957", "SRR13748118",
    "SRR18100902", "SRR18969728", "SRR20746842", "ERR3213218", "ERR5261688",
    "ERR7764284", "ERR12018803", "ERR11513061", "ERR12075434", "ERR14747360",
    "SRR28820025", "SRR29660141", "SRR31928344", "SRR34680179", "SRR35699594",
    "SRR12390960", "SRR18100905", "SRR20746885", "ERR3213230", "ERR5261691",
    "ERR7764305", "ERR12018804", "ERR11513069", "ERR12075448", "ERR14747370",
    "SRR28820027", "SRR29660143", "SRR31928354", "SRR34680180", "SRR35699595",
    "SRR18100906", "SRR20746889", "ERR3213293", "ERR5261696", "ERR7764316",
    "ERR12018815", "ERR11513071", "ERR12075449", "SRR28820028", "SRR29660144",
    "SRR31928413", "SRR35699596", "SRR18100907", "SRR20746897", "ERR3213758",
    "ERR5261702", "ERR7764443", "ERR12018823", "ERR12075453", "SRR28820031",
    "SRR29660159", "SRR31928420", "SRR35699600", "SRR18100910", "SRR20746898",
    "ERR3213760", "ERR5261708", "ERR7764448", "ERR12018829", "ERR12075454",
    "SRR28820034", "SRR29660161", "SRR31928430", "SRR35699601", "SRR18100911",
    "SRR20746899", "ERR3213762", "ERR5261711", "ERR7764461", "ERR12018830",
    "SRR28820043", "SRR31928434", "SRR35699602", "SRR18100915", "SRR20746904",
    "ERR3213808", "ERR5261715", "ERR7764550", "ERR12018832", "SRR28820046",
    "SRR31928518", "SRR35699603", "SRR18100916", "SRR20746913", "ERR3213841",
    "ERR5261716", "ERR7764555", "ERR12018861",
]


def query_ena_filereport(accession: str) -> dict | None:
    """Query ENA Portal API for FTP URL and file size."""
    url = (
        "https://www.ebi.ac.uk/ena/portal/api/filereport"
        f"?accession={accession}"
        "&result=read_run"
        "&fields=run_accession,fastq_ftp,fastq_bytes,instrument_platform,"
        "library_source,library_strategy,base_count"
        "&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data:
            return None
        row = data[0]
        ftps = [f.strip() for f in row.get('fastq_ftp', '').split(';') if f.strip()]
        sizes = [int(s) for s in row.get('fastq_bytes', '').split(';') if s.strip().isdigit()]
        if not ftps or not sizes:
            return None
        # Prefer single-file (ONT is usually one FASTQ)
        # If multiple files, take the largest
        pairs = sorted(zip(sizes, ftps), reverse=True)
        total_size = sum(sizes)
        return {
            'accession': accession,
            'ftp_url': 'ftp://' + pairs[0][1],
            'total_bytes': total_size,
            'platform': row.get('instrument_platform', ''),
            'source': row.get('library_source', ''),
            'strategy': row.get('library_strategy', ''),
        }
    except Exception as e:
        log.debug(f"ENA query failed for {accession}: {e}")
        return None


def download_ftp(ftp_url: str, dest_path: Path) -> bool:
    """Download a file via wget from FTP."""
    if dest_path.exists() and dest_path.stat().st_size > MIN_BYTES // 2:
        log.info(f"  Already downloaded: {dest_path.name}")
        return True
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    log.info(f"  Downloading {ftp_url} -> {dest_path.name}")
    cmd = [
        'wget', '-q', '--show-progress',
        '-O', str(dest_path),
        ftp_url,
    ]
    result = subprocess.run(cmd, timeout=7200)  # 2h timeout
    if result.returncode != 0 or not dest_path.exists() or dest_path.stat().st_size == 0:
        log.error(f"  wget failed (rc={result.returncode})")
        if dest_path.exists():
            dest_path.unlink()
        return False
    log.info(f"  Downloaded: {dest_path.stat().st_size / 1e9:.2f} GB")
    return True


async def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    minio = Minio(
        os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
        access_key=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
        secret_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
        secure=False,
    )
    if not minio.bucket_exists(BUCKET):
        minio.make_bucket(BUCKET)

    dsn = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
        f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    conn = await asyncpg.connect(dsn)

    bucket_id = await conn.fetchval(
        "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1", BUCKET
    )
    loc_id = await conn.fetchval("SELECT location_id FROM locations LIMIT 1")

    log.info("=" * 70)
    log.info("  DOWNLOAD + QUEUE: 100 Environmental Metagenomics ONT Samples")
    log.info("=" * 70)
    log.info(f"  Candidates: {len(CANDIDATES)}")
    log.info(f"  Target size: {MIN_BYTES/1e9:.1f} – {MAX_BYTES/1e9:.1f} GB")
    log.info(f"  Target count: {TARGET_COUNT}")
    log.info("")

    # Phase 1: Query ENA for real FTP paths and sizes
    log.info("Phase 1: Querying ENA for file info...")
    valid = []
    for acc in CANDIDATES:
        if len(valid) >= TARGET_COUNT + 20:  # get a few extras
            break
        info = query_ena_filereport(acc)
        if info is None:
            log.debug(f"  {acc}: not found on ENA")
            continue
        if not (MIN_BYTES <= info['total_bytes'] <= MAX_BYTES):
            log.debug(f"  {acc}: size {info['total_bytes']/1e9:.2f} GB out of range")
            continue
        if info['platform'].upper() not in ('OXFORD_NANOPORE', 'NANOPORE', ''):
            log.debug(f"  {acc}: platform={info['platform']} skipping")
            continue
        # Check not already completed
        existing = await conn.fetchval(
            """
            SELECT pr.pipeline_id FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE s.sample_code = $1 AND pr.status IN ('completed', 'running', 'queued')
            """, acc
        )
        if existing:
            log.info(f"  {acc}: pipeline already exists (id={existing}), skipping")
            continue
        log.info(f"  {acc}: {info['total_bytes']/1e9:.2f} GB  OK")
        valid.append(info)
        time.sleep(0.3)  # polite rate limit

    log.info(f"\nPhase 1 done: {len(valid)} valid samples found")

    # Trim to target
    valid = valid[:TARGET_COUNT]

    # Phase 2: Download, upload, queue
    log.info(f"\nPhase 2: Downloading and queuing {len(valid)} samples...")
    queued = 0
    failed = 0

    for idx, info in enumerate(valid, 1):
        acc = info['accession']
        ftp_url = info['ftp_url']
        file_name = ftp_url.split('/')[-1]
        local_path = DOWNLOAD_DIR / acc / file_name
        object_key = f"{acc}/raw/{file_name}"

        log.info(f"\n[{idx}/{len(valid)}] {acc}  ({info['total_bytes']/1e9:.2f} GB)")

        # Check if already in MinIO
        try:
            stat = minio.stat_object(BUCKET, object_key)
            log.info(f"  Already in MinIO ({stat.size/1e9:.2f} GB)")
        except Exception:
            # Download
            if not download_ftp(ftp_url, local_path):
                log.error(f"  SKIP {acc}: download failed")
                failed += 1
                continue

            # Upload to MinIO
            log.info(f"  Uploading to MinIO Bronze...")
            try:
                minio.fput_object(BUCKET, object_key, str(local_path), content_type='application/gzip')
                stat = minio.stat_object(BUCKET, object_key)
                log.info(f"  Uploaded: {stat.size/1e9:.2f} GB")
            except Exception as e:
                log.error(f"  MinIO upload failed: {e}")
                failed += 1
                continue
            finally:
                if DELETE_AFTER_UPLOAD and local_path.exists():
                    local_path.unlink()
                    # Remove empty dir
                    try:
                        local_path.parent.rmdir()
                    except Exception:
                        pass

        # Get or create sample record
        sample_id = await conn.fetchval(
            "SELECT sample_id FROM samples WHERE sample_code = $1", acc
        )
        if not sample_id:
            sample_id = await conn.fetchval(
                """
                INSERT INTO samples (
                    sample_code, collection_date, sample_type,
                    sequencing_platform, location_id
                ) VALUES ($1, $2, 'environmental', 'nanopore', $3)
                RETURNING sample_id
                """,
                acc, date.today(), loc_id,
            )
            log.info(f"  Created sample (id={sample_id})")
        else:
            log.info(f"  Sample exists (id={sample_id})")

        # Cancel any stale queued/failed pipelines for this sample
        await conn.execute(
            """
            UPDATE pipeline_runs SET status = 'cancelled'
            WHERE sample_id = $1 AND status IN ('queued', 'failed', 'pending')
            """, sample_id
        )

        # Create pipeline run
        results_path = f"/tmp/nextflow/{acc}/results"
        pipeline_id = await conn.fetchval(
            """
            INSERT INTO pipeline_runs (
                sample_id, sample_name, pipeline_name, status, results_path
            ) VALUES ($1, $2, 'nextflow_pipeline', 'pending', $3)
            RETURNING pipeline_id
            """,
            sample_id, acc, results_path,
        )

        # Register minio_object
        stat = minio.stat_object(BUCKET, object_key)
        await conn.execute(
            """
            INSERT INTO minio_objects (
                bucket_id, object_key, object_name, object_size_bytes,
                content_type, etag, sample_id, pipeline_id, layer_stage
            ) VALUES ($1, $2, $3, $4, 'application/gzip', $5, $6, $7, 'raw')
            ON CONFLICT DO NOTHING
            """,
            bucket_id, object_key, file_name,
            stat.size, stat.etag, sample_id, pipeline_id,
        )

        # Enqueue via RQ
        try:
            job = enqueue_pipeline(
                pipeline_id=pipeline_id,
                sample_code=acc,
                input_dir=f"{BUCKET}/{acc}/raw/",
                output_dir=results_path,
                params={},
            )
            job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
            await conn.execute(
                "UPDATE pipeline_runs SET status='queued', job_id=$1 WHERE pipeline_id=$2",
                job_id, pipeline_id,
            )
            queued += 1
            log.info(f"  Queued: pipeline_id={pipeline_id}, job={job_id[:16]}...")
        except Exception as e:
            log.error(f"  Enqueue failed: {e}")
            failed += 1

        if WAIT_BETWEEN:
            time.sleep(WAIT_BETWEEN)

    # Final summary
    await conn.close()
    log.info("\n" + "=" * 70)
    log.info("  DONE")
    log.info("=" * 70)
    log.info(f"  Queued:  {queued}")
    log.info(f"  Failed:  {failed}")
    log.info(f"  Total:   {len(valid)}")
    log.info("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())

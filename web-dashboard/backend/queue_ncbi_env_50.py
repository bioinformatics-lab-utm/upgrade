#!/usr/bin/env python3
"""
Download and queue 50 environmental ONT metagenomics samples from NCBI (via ENA FTP mirror).
Run inside backend container:
  docker exec -d upgrade_web_backend python3 /app/queue_ncbi_env_50.py
Logs: docker exec upgrade_web_backend tail -f /tmp/queue_ncbi_env_50.log
"""
import asyncio, os, sys, subprocess, logging, time, json, urllib.request
from pathlib import Path

sys.path.insert(0, '/app')
os.chdir('/app')

import asyncpg
from minio import Minio
from tasks.pipeline_tasks import enqueue_pipeline
from config import config

DOWNLOAD_DIR = Path('/data/ncbi_env_50')
BUCKET = 'genomic-bronze'
DELETE_AFTER_UPLOAD = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/queue_ncbi_env_50.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# 50 environmental ONT metagenomics samples from NCBI (1-2 GB each)
ACCESSIONS = [
    'SRR36743559', 'SRR36743504', 'SRR34009681', 'SRR19049537', 'SRR25230045',
    'SRR36743233', 'SRR36743520', 'SRR32726890', 'SRR32852251', 'SRR36743219',
    'SRR36743251', 'SRR36743505', 'SRR32852255', 'SRR25230061', 'SRR21374133',
    'SRR32852252', 'SRR25230031', 'SRR25230043', 'SRR21374135', 'SRR33471298',
    'SRR25230039', 'SRR36743534', 'SRR25230049', 'SRR25230050', 'SRR25230072',
    'SRR25230080', 'SRR25230026', 'SRR32726892', 'SRR25230084', 'SRR25230042',
    'SRR25230047', 'SRR21374130', 'SRR25230079', 'SRR25230087', 'SRR25230053',
    'SRR36743229', 'SRR32726886', 'SRR36743498', 'SRR36743523', 'SRR25230058',
    'SRR36743517', 'SRR32022277', 'SRR25230055', 'SRR13009788', 'SRR25230085',
    'SRR34009686', 'SRR25230046', 'SRR25230044', 'SRR36743515', 'SRR34009683',
]


def get_ena_ftp(acc: str) -> list[str]:
    """Query ENA for FTP download URLs of an SRR accession."""
    url = (
        f'https://www.ebi.ac.uk/ena/portal/api/search?result=read_run'
        f'&query=run_accession%3D%22{acc}%22'
        f'&fields=run_accession,fastq_ftp,fastq_bytes&format=json&limit=1'
    )
    try:
        req = urllib.request.Request(url, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        if isinstance(data, list) and data:
            ftp = data[0].get('fastq_ftp', '')
            urls = [f'ftp://{u}' for u in ftp.split(';') if u.strip()]
            return urls
    except Exception as e:
        log.warning(f'[{acc}] ENA lookup failed: {e}')
    return []


def curl_download(url: str, dest: Path) -> bool:
    """Download file with curl, resume if partial."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        'curl', '-C', '-', '-L', '--retry', '3', '--retry-delay', '5',
        '--max-time', '7200', '-o', str(dest), url
    ]
    log.info(f'  curl {url} → {dest.name}')
    r = subprocess.run(cmd, capture_output=True, timeout=7300)
    if r.returncode != 0:
        log.warning(f'  curl failed (rc={r.returncode}): {r.stderr.decode()[:200]}')
        return False
    return dest.exists() and dest.stat().st_size > 100_000


def download_sample(acc: str) -> Path | None:
    """Download FASTQ.gz for acc, merge if multiple files, return final path."""
    out_gz = DOWNLOAD_DIR / f'{acc}.fastq.gz'
    if out_gz.exists() and out_gz.stat().st_size > 100_000_000:
        log.info(f'[{acc}] Already on disk ({out_gz.stat().st_size/1e9:.2f} GB)')
        return out_gz

    ftp_urls = get_ena_ftp(acc)
    if not ftp_urls:
        log.error(f'[{acc}] No FTP URLs found in ENA')
        return None

    log.info(f'[{acc}] FTP URLs: {ftp_urls}')

    if len(ftp_urls) == 1:
        ok = curl_download(ftp_urls[0], out_gz)
        return out_gz if ok else None

    # Multiple files (split reads) — download each then merge
    parts = []
    for i, url in enumerate(ftp_urls):
        part = DOWNLOAD_DIR / f'{acc}_part{i}.fastq.gz'
        if not (part.exists() and part.stat().st_size > 100_000):
            if not curl_download(url, part):
                log.error(f'[{acc}] Failed to download part {i}: {url}')
                return None
        parts.append(part)

    log.info(f'[{acc}] Merging {len(parts)} parts → {out_gz.name}')
    with open(out_gz, 'wb') as fout:
        for part in parts:
            with open(part, 'rb') as fin:
                while True:
                    chunk = fin.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
            part.unlink(missing_ok=True)

    return out_gz if out_gz.exists() and out_gz.stat().st_size > 100_000_000 else None


async def process_sample(acc: str, conn, minio_client) -> bool:
    # Skip if already in DB
    if await conn.fetchval("SELECT sample_id FROM samples WHERE sample_code = $1", acc):
        log.info(f'[{acc}] Already in DB, skipping')
        return False

    fastq_path = download_sample(acc)
    if not fastq_path:
        log.error(f'[{acc}] Download failed')
        return False

    file_size = fastq_path.stat().st_size
    log.info(f'[{acc}] Downloaded: {file_size/1e9:.2f} GB')

    # Upload to MinIO Bronze
    object_key = f'{acc}/raw/{fastq_path.name}'
    try:
        minio_client.fput_object(BUCKET, object_key, str(fastq_path),
                                 content_type='application/gzip')
        log.info(f'[{acc}] Uploaded → s3://{BUCKET}/{object_key}')
    except Exception as e:
        log.error(f'[{acc}] MinIO upload error: {e}')
        return False

    if DELETE_AFTER_UPLOAD:
        fastq_path.unlink(missing_ok=True)

    # DB + queue
    try:
        sample_id = await conn.fetchval("""
            INSERT INTO samples (sample_code, sample_name, sample_type, sequencing_platform, created_at)
            VALUES ($1, $2, 'environmental', 'Oxford Nanopore', NOW())
            ON CONFLICT (sample_code) DO UPDATE SET sample_code = EXCLUDED.sample_code
            RETURNING sample_id
        """, acc, acc)

        pipeline_id = await conn.fetchval("""
            INSERT INTO pipeline_runs
                (sample_id, sample_name, status, results_path, created_at, queued_at)
            VALUES ($1, $2, 'queued', $3, NOW(), NOW())
            RETURNING pipeline_id
        """, sample_id, acc, f's3://{BUCKET}/{object_key}')

        enqueue_pipeline(
            pipeline_id=pipeline_id,
            sample_name=acc,
            fastq_path=f's3://{BUCKET}/{object_key}',
            sample_id=sample_id,
        )
        log.info(f'[{acc}] Queued as pipeline_id={pipeline_id}')
        return True
    except Exception as e:
        log.error(f'[{acc}] DB/queue error: {e}')
        return False


async def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dsn = f'postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}'
    conn = await asyncpg.connect(dsn)
    minio_client = Minio(
        os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
        access_key=os.environ['MINIO_ROOT_USER'],
        secret_key=os.environ['MINIO_ROOT_PASSWORD'],
        secure=False,
    )
    if not minio_client.bucket_exists(BUCKET):
        minio_client.make_bucket(BUCKET)

    queued, failed, skipped = 0, 0, 0
    for i, acc in enumerate(ACCESSIONS, 1):
        log.info(f'=== [{i}/{len(ACCESSIONS)}] {acc} ===')
        try:
            ok = await process_sample(acc, conn, minio_client)
            if ok:
                queued += 1
                time.sleep(2)
            else:
                skipped += 1
        except Exception as e:
            log.error(f'[{acc}] Unexpected: {e}')
            failed += 1

    await conn.close()
    log.info(f'=== DONE: queued={queued} skipped={skipped} failed={failed} ===')


if __name__ == '__main__':
    asyncio.run(main())

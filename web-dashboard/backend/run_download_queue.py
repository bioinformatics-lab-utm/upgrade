#!/usr/bin/env python3
"""
Read ena_valid.json, download first 100 samples, upload to MinIO, queue pipelines.
Runs inside backend container. Uses curl (no wget).
"""
import asyncio, os, sys, json, subprocess, time, logging
from pathlib import Path
from datetime import date

sys.path.insert(0, '/app')
os.chdir('/app')

import asyncpg
from minio import Minio
from tasks.pipeline_tasks import enqueue_pipeline
from config import config

BUCKET = 'genomic-bronze'
DOWNLOAD_DIR = Path('/data/env_metagenomes')
TARGET = 100
DELETE_AFTER = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/download_queue.log'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def curl_download(ftp_url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 500_000_000:
        log.info(f"  Already have {dest.name} ({dest.stat().st_size/1e9:.2f}GB)")
        return True
    full_url = 'ftp://' + ftp_url
    log.info(f"  curl {full_url}")
    r = subprocess.run(
        ['curl', '-C', '-', '-L', '--retry', '3', '--retry-delay', '10',
         '--progress-bar', '-o', str(dest), full_url],
        timeout=7200,
    )
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size < 100_000:
        log.error(f"  curl failed rc={r.returncode}")
        dest.unlink(missing_ok=True)
        return False
    log.info(f"  Downloaded {dest.stat().st_size/1e9:.2f}GB")
    return True


async def main():
    with open('/tmp/ena_valid.json') as f:
        candidates = json.load(f)[:TARGET]

    log.info(f"Processing {len(candidates)} samples (~{sum(c['bytes'] for c in candidates)/1e9:.1f}GB total)")

    minio = Minio(
        os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
        access_key=os.environ['MINIO_ROOT_USER'],
        secret_key=os.environ['MINIO_ROOT_PASSWORD'],
        secure=False,
    )
    if not minio.bucket_exists(BUCKET):
        minio.make_bucket(BUCKET)

    dsn = (f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}"
           f"@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}")
    conn = await asyncpg.connect(dsn)

    bucket_id = await conn.fetchval(
        "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1", BUCKET
    )
    loc_id = await conn.fetchval("SELECT location_id FROM locations LIMIT 1")

    queued = failed = skipped = 0

    for idx, info in enumerate(candidates, 1):
        acc = info['acc']
        ftps = info['ftp']
        if not ftps:
            log.warning(f"[{idx}] {acc}: no FTP URL, skip")
            skipped += 1
            continue

        ftp_url = ftps[0]
        file_name = ftp_url.split('/')[-1]
        object_key = f"{acc}/raw/{file_name}"
        local_path = DOWNLOAD_DIR / acc / file_name

        log.info(f"\n[{idx}/{len(candidates)}] {acc}  ({info['bytes']/1e9:.2f}GB)")

        # Check already active pipeline
        existing = await conn.fetchval(
            """SELECT pr.pipeline_id FROM pipeline_runs pr
               JOIN samples s ON s.sample_id=pr.sample_id
               WHERE s.sample_code=$1 AND pr.status IN ('completed','running','queued')""",
            acc
        )
        if existing:
            log.info(f"  Pipeline {existing} already active, skip")
            skipped += 1
            continue

        # Check MinIO
        in_minio = False
        try:
            stat = minio.stat_object(BUCKET, object_key)
            log.info(f"  Already in MinIO ({stat.size/1e9:.2f}GB)")
            in_minio = True
        except Exception:
            pass

        if not in_minio:
            if not curl_download(ftp_url, local_path):
                failed += 1
                continue
            log.info("  Uploading to MinIO...")
            try:
                minio.fput_object(BUCKET, object_key, str(local_path),
                                  content_type='application/gzip')
                stat = minio.stat_object(BUCKET, object_key)
                log.info(f"  Uploaded {stat.size/1e9:.2f}GB")
            except Exception as e:
                log.error(f"  MinIO upload failed: {e}")
                failed += 1
                continue
            finally:
                if DELETE_AFTER and local_path.exists():
                    local_path.unlink()
                    try: local_path.parent.rmdir()
                    except: pass

        # Get/create sample
        sample_id = await conn.fetchval(
            "SELECT sample_id FROM samples WHERE sample_code=$1", acc
        )
        if not sample_id:
            sample_id = await conn.fetchval(
                """INSERT INTO samples (sample_code,collection_date,sample_type,
                   sequencing_platform,location_id)
                   VALUES ($1,$2,'environmental','nanopore',$3)
                   RETURNING sample_id""",
                acc, date.today(), loc_id,
            )
            log.info(f"  Created sample id={sample_id}")
        else:
            log.info(f"  Sample id={sample_id}")

        # Cancel stale pipelines
        await conn.execute(
            "UPDATE pipeline_runs SET status='cancelled' WHERE sample_id=$1 AND status IN ('queued','failed','pending')",
            sample_id
        )

        # Create pipeline run
        results_path = f"/tmp/nextflow/{acc}/results"
        pipeline_id = await conn.fetchval(
            """INSERT INTO pipeline_runs (sample_id,sample_name,pipeline_name,status,results_path)
               VALUES ($1,$2,'nextflow_pipeline','pending',$3) RETURNING pipeline_id""",
            sample_id, acc, results_path,
        )

        # Register minio_object
        stat = minio.stat_object(BUCKET, object_key)
        await conn.execute(
            """INSERT INTO minio_objects (bucket_id,object_key,object_name,object_size_bytes,
               content_type,etag,sample_id,pipeline_id,layer_stage)
               VALUES ($1,$2,$3,$4,'application/gzip',$5,$6,$7,'raw') ON CONFLICT DO NOTHING""",
            bucket_id, object_key, file_name, stat.size, stat.etag, sample_id, pipeline_id,
        )

        # Enqueue
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
                "UPDATE pipeline_runs SET status='queued',job_id=$1 WHERE pipeline_id=$2",
                job_id, pipeline_id,
            )
            queued += 1
            log.info(f"  Queued pipeline_id={pipeline_id} job={job_id[:16]}...")
        except Exception as e:
            log.error(f"  Enqueue failed: {e}")
            failed += 1

        time.sleep(1)

    await conn.close()
    log.info(f"\n{'='*60}")
    log.info(f"DONE: queued={queued}, failed={failed}, skipped={skipped}")
    log.info(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())

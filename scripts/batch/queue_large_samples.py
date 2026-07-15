#!/usr/bin/env python3
"""
Upload large environmental metagenome samples to MinIO Bronze
and queue them via API pipeline.

Usage (inside backend container or with API):
  python3 scripts/batch/queue_large_samples.py
"""
import asyncio
import os
import sys
import glob

sys.path.insert(0, '/app')
os.chdir('/app')

import asyncpg
from minio import Minio
from minio.commonconfig import Tags
from datetime import date
from tasks.pipeline_tasks import enqueue_pipeline
from config import config

SAMPLES_DIR = '/data/large_samples'

SAMPLE_METADATA = {
    'SRR29656297': {'location': 'Atlantic Ocean', 'type': 'seawater'},
    'SRR32022376': {'location': 'WWTP Influent',  'type': 'wastewater'},
    'SRR32022383': {'location': 'WWTP Effluent',  'type': 'wastewater'},
    'SRR28272155': {'location': 'Greenland Ice',  'type': 'ice_core'},
    'SRR32022268': {'location': 'WWTP Mixed',     'type': 'wastewater'},
    'SRR32228745': {'location': 'Liquid Enrichment', 'type': 'wastewater'},
    'SRR36990185': {'location': 'Lake Water',     'type': 'freshwater'},
    'SRR14085590': {'location': 'Shotgun Metagenome', 'type': 'environmental'},
    'SRR14307795': {'location': 'Microbial Community', 'type': 'environmental'},
    'SRR30574959': {'location': 'Activated Sludge', 'type': 'wastewater'},
}


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

    # Ensure genomic-bronze bucket exists
    if not minio.bucket_exists('genomic-bronze'):
        minio.make_bucket('genomic-bronze')
        print("Created genomic-bronze bucket")

    bucket_id = await conn.fetchval(
        "SELECT bucket_id FROM minio_buckets WHERE bucket_name = 'genomic-bronze'"
    )

    # Get or create a default location
    loc_id = await conn.fetchval("SELECT location_id FROM locations LIMIT 1")

    queued = 0
    for sample_code, meta in SAMPLE_METADATA.items():
        fastq_path = os.path.join(SAMPLES_DIR, sample_code, f'{sample_code}.fastq.gz')
        if not os.path.exists(fastq_path):
            print(f"  SKIP {sample_code}: file not found at {fastq_path}")
            continue

        file_size = os.path.getsize(fastq_path)
        print(f"\n[{sample_code}] {file_size/1e9:.2f}GB - uploading to Bronze...")

        # Upload to MinIO Bronze
        object_key = f"{sample_code}/raw/{sample_code}.fastq.gz"
        minio.fput_object(
            'genomic-bronze', object_key, fastq_path,
            content_type='application/gzip',
        )
        print(f"  ✓ Uploaded to Bronze: {object_key}")

        # Insert/get sample record
        sample_id = await conn.fetchval(
            "SELECT sample_id FROM samples WHERE sample_code = $1", sample_code
        )
        if not sample_id:
            sample_id = await conn.fetchval("""
                INSERT INTO samples (
                    sample_code, collection_date, sample_type,
                    sequencing_platform, location_id
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING sample_id
            """,
                sample_code,
                date.today(),
                meta['type'],
                'nanopore',
                loc_id,
            )
            print(f"  ✓ Created sample record (id={sample_id})")
        else:
            print(f"  ✓ Sample exists (id={sample_id})")

        # Create pipeline run
        pipeline_id = await conn.fetchval("""
            INSERT INTO pipeline_runs (
                sample_id, sample_name, pipeline_name, status,
                results_path
            ) VALUES ($1, $2, 'nextflow_pipeline', 'pending', $3)
            RETURNING pipeline_id
        """,
            sample_id,
            sample_code,
            f'/results/{sample_code}',
        )

        # Register minio_object
        stat = minio.stat_object('genomic-bronze', object_key)
        await conn.execute("""
            INSERT INTO minio_objects (
                bucket_id, object_key, object_name, object_size_bytes,
                content_type, etag, sample_id, pipeline_id, layer_stage
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'raw')
            ON CONFLICT DO NOTHING
        """,
            bucket_id, object_key, f'{sample_code}.fastq.gz',
            stat.size, 'application/gzip', stat.etag,
            sample_id, pipeline_id,
        )

        # Enqueue via RQ
        job = enqueue_pipeline(
            pipeline_id=pipeline_id,
            sample_code=sample_code,
            input_dir=f'genomic-bronze/{sample_code}/raw/',
            output_dir=f'/tmp/nextflow/{sample_code}/results',
            params={},
        )
        job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
        await conn.execute(
            "UPDATE pipeline_runs SET status='queued', job_id=$1 WHERE pipeline_id=$2",
            job_id, pipeline_id
        )

        queued += 1
        print(f"  ✓ Queued (pipeline_id={pipeline_id}, job={job_id[:16]}...)")

    await conn.close()
    print(f"\nDone: {queued}/{len(SAMPLE_METADATA)} samples queued")


if __name__ == '__main__':
    asyncio.run(main())

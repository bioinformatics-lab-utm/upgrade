#!/usr/bin/env python3
"""
Direct pipeline launch via RQ (bypasses API complexity)
Requires: Pipeline record in DB, then enqueue to RQ
"""
import sys
import os

# Add backend to path
sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

from redis import Redis
from rq import Queue

# Read Redis password
with open('/home/nicolaedrabcinski/upgrade/secrets/redis_password') as f:
    redis_password = f.read().strip()

# Connect to Redis
redis_conn = Redis(
    host='localhost',
    port=6379,
    password=redis_password,
    db=0,
    decode_responses=False
)

# Import task
from tasks.pipeline_tasks import run_nextflow_pipeline

# Get queue
queue = Queue('pipeline-queue', connection=redis_conn)

# Enqueue Pipeline #67 with 12h timeout
print("=" * 60)
print("DIRECT PIPELINE LAUNCH (RQ)")
print("=" * 60)
print("\nEnqueuing Pipeline #67...")

job = queue.enqueue(
    run_nextflow_pipeline,
    pipeline_id=67,
    sample_code='ZYMO_API_001',
    input_dir='/data/zymo_mock',
    output_dir='/results/zymo_api_001',
    params={
        'flye_genome_size': '50m',
        'flye_meta': True,
        'threads': 32
    },
    job_timeout=43200,  # 12 hours
    result_ttl=86400,
    failure_ttl=86400
)

job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id

print("=" * 60)
print("✓ PIPELINE #67 ENQUEUED SUCCESSFULLY")
print("=" * 60)
print(f"Job ID:       {job_id}")
print(f"Job Timeout:  43200s (12 hours)")
print(f"Sample:       ZYMO_API_001")
print(f"Input:        /data/zymo_mock")
print(f"Output:       /results/zymo_api_001")
print(f"\nPipeline will use -resume flag to skip cached stages:")
print("  ✓ FILTLONG  (cached)")
print("  ✓ NANOPLOT  (cached)")
print("  ✓ FLYE      (cached - 56.3 Mbp assembly)")
print("  ⏳ MetaBAT2, CheckM, Prokka, DeepARG, ABRicate (remaining)")
print("=" * 60)

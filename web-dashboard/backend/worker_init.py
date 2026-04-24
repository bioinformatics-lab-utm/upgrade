#!/usr/bin/env python3
"""
RQ Worker initialization script - synchronous
"""
import os
import sys
import logging
from redis import Redis
from rq import Worker, Queue

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def read_secret(secret_path):
    """Read a secret from a Docker secrets file."""
    try:
        with open(secret_path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        logger.warning(f"Failed to read secret from {secret_path}: {e}")
        return None

def main():
    logger.info("Starting RQ worker...")

    # 1. Docker secrets override env vars
    redis_password = read_secret('/run/secrets/redis_password')
    postgres_password = read_secret('/run/secrets/postgres_password')
    minio_root_password = read_secret('/run/secrets/minio_root_password')

    if redis_password:
        os.environ['REDIS_PASSWORD'] = redis_password
    if postgres_password:
        os.environ['POSTGRES_PASSWORD'] = postgres_password
    if minio_root_password:
        os.environ['MINIO_ROOT_PASSWORD'] = minio_root_password

    # 2. Connect to Redis
    redis_host = os.environ.get('REDIS_HOST', 'redis')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    redis_pass = redis_password or os.environ.get('REDIS_PASSWORD')

    logger.info(f"Connecting to Redis at {redis_host}:{redis_port}")

    try:
        redis_conn = Redis(
            host=redis_host,
            port=redis_port,
            password=redis_pass,
            decode_responses=False  # RQ uses binary serialization
        )

        if redis_conn.ping():
            logger.info("✓ Successfully connected to Redis")
        else:
            logger.error("✗ Redis ping failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"✗ Failed to connect to Redis: {e}")
        sys.exit(1)

    # 3. Queue settings
    queue_name = os.environ.get('RQ_QUEUE_NAME', 'pipeline-queue')
    job_timeout = int(os.environ.get('RQ_JOB_TIMEOUT', 43200))  # 12 hours default

    logger.info(f"Listening to queue: {queue_name}")
    logger.info(f"Default job timeout: {job_timeout}s ({job_timeout//3600}h)")

    # 4. Start worker
    queues = [Queue(name=queue_name, connection=redis_conn)]
    worker = Worker(
        queues,
        connection=redis_conn,
        default_worker_ttl=job_timeout,
        default_result_ttl=86400  # Keep results for 24h
    )
    logger.info("✓ RQ worker started successfully")
    worker.work()

if __name__ == '__main__':
    main()

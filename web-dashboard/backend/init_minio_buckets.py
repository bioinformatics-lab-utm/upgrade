#!/usr/bin/env python3
"""
Initialize MinIO buckets for UPGRADE lakehouse architecture
Run this on startup to ensure all required buckets exist
"""
import sys
import time
from minio_helper import get_minio_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_BUCKETS = [
    'genomic-bronze',
    'genomic-silver',
    'genomic-gold',
    'weather-data'
]

def init_buckets(max_retries=5):
    """Initialize all required MinIO buckets with retries"""

    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to MinIO (attempt {attempt + 1}/{max_retries})...")
            minio_client = get_minio_client()

            for bucket_name in REQUIRED_BUCKETS:
                if minio_client.client.bucket_exists(bucket_name):
                    logger.info(f"✓ Bucket '{bucket_name}' already exists")
                else:
                    logger.info(f"Creating bucket '{bucket_name}'...")
                    minio_client.client.make_bucket(bucket_name)
                    logger.info(f"✓ Created bucket '{bucket_name}'")

            logger.info("✅ All MinIO buckets initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize buckets (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries reached. MinIO initialization failed.")
                return False

    return False

if __name__ == "__main__":
    success = init_buckets()
    sys.exit(0 if success else 1)

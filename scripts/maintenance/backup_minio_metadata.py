#!/usr/bin/env python3
"""
MinIO Metadata Backup Script

Exports MinIO bucket metadata to JSON for backup/disaster recovery:
- Bucket configuration
- Object list with metadata (etag, size, modified date)
- Retention policies
- Versioning status

Usage:
    python scripts/backup_minio_metadata.py [--output backups/minio_metadata.json]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from minio import Minio
from minio.error import S3Error

# Load environment from .env
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:
                    os.environ[key] = value

MINIO_ENDPOINT = os.environ.get('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.environ.get('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin')
MINIO_SECURE = os.environ.get('MINIO_SECURE', 'false').lower() == 'true'
BUCKETS = ['genomic-bronze', 'genomic-silver', 'genomic-gold']


def parse_args():
    parser = argparse.ArgumentParser(description="Backup MinIO metadata to JSON")
    parser.add_argument('--output', type=str, default='backups/minio/metadata_backup.json', 
                       help='Output JSON file path')
    return parser.parse_args()


def get_minio_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )


def backup_bucket_metadata(client, bucket_name):
    """
    Backup metadata for a single bucket
    """
    metadata = {
        'bucket_name': bucket_name,
        'exists': False,
        'versioning': None,
        'objects': []
    }
    
    try:
        # Check if bucket exists
        if not client.bucket_exists(bucket_name):
            print(f"⚠️  Bucket {bucket_name} does not exist")
            return metadata
        
        metadata['exists'] = True
        
        # Get versioning status
        try:
            versioning = client.get_bucket_versioning(bucket_name)
            metadata['versioning'] = {
                'status': versioning.status if versioning else 'Disabled',
                'mfa_delete': versioning.mfa_delete if versioning and hasattr(versioning, 'mfa_delete') else None
            }
        except Exception as e:
            print(f"  Could not get versioning for {bucket_name}: {e}")
        
        # List all objects
        print(f"  Backing up objects from {bucket_name}...")
        object_count = 0
        for obj in client.list_objects(bucket_name, recursive=True):
            metadata['objects'].append({
                'object_name': obj.object_name,
                'size': obj.size,
                'etag': obj.etag,
                'last_modified': obj.last_modified.isoformat() if obj.last_modified else None,
                'content_type': obj.content_type,
                'version_id': obj.version_id if hasattr(obj, 'version_id') else None,
                'is_delete_marker': obj.is_delete_marker if hasattr(obj, 'is_delete_marker') else False
            })
            object_count += 1
        
        print(f"  ✓ {bucket_name}: {object_count} objects")
        
    except S3Error as e:
        print(f"  Error accessing bucket {bucket_name}: {e}")
    except Exception as e:
        print(f"  Unexpected error for bucket {bucket_name}: {e}")
    
    return metadata


def main():
    args = parse_args()
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting MinIO metadata backup to {output_file}")
    print(f"Endpoint: {MINIO_ENDPOINT}")
    
    # Connect to MinIO
    try:
        client = get_minio_client()
    except Exception as e:
        print(f"✗ Failed to connect to MinIO: {e}")
        return 1
    
    # Backup metadata
    backup_data = {
        'backup_timestamp': datetime.now(timezone.utc).isoformat(),
        'minio_endpoint': MINIO_ENDPOINT,
        'buckets': []
    }
    
    for bucket in BUCKETS:
        print(f"\nBacking up bucket: {bucket}")
        bucket_metadata = backup_bucket_metadata(client, bucket)
        backup_data['buckets'].append(bucket_metadata)
    
    # Write to JSON file
    with open(output_file, 'w') as f:
        json.dump(backup_data, f, indent=2)
    
    total_objects = sum(len(b['objects']) for b in backup_data['buckets'])
    print(f"\n✓ Backup complete: {len(backup_data['buckets'])} buckets, {total_objects} objects")
    print(f"  Saved to: {output_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
# Retention Policy Script - Docker Version
# Runs the Python retention script inside Docker with proper network/credentials access

set -e

DAYS=${1:-180}
DRY_RUN=${2:---dry-run}

echo "Running retention policy (${DAYS} days retention, ${DRY_RUN})"

# Use postgres container since backend is not running
docker compose exec -T postgres python3 -c "
import asyncio
import asyncpg
from datetime import datetime, timedelta, timezone
from config import config

async def cleanup_db(cutoff, dry_run=True):
    conn = await asyncpg.connect(config.DATABASE_URL)
    
    # Find old minio_objects
    old_objects = await conn.fetch('''
        SELECT object_id, object_key, created_at FROM minio_objects WHERE created_at < \$1
    ''', cutoff)
    print(f'Found {len(old_objects)} old minio_objects')
    
    if dry_run:
        for obj in old_objects:
            print(f\"Would delete DB object_id={obj['object_id']} key={obj['object_key']} created_at={obj['created_at']}\")
    else:
        if old_objects:
            object_ids = [o['object_id'] for o in old_objects]
            # Delete lineage first (foreign key constraint)
            await conn.execute('DELETE FROM data_lineage WHERE target_object_id = ANY(\$1)', object_ids)
            await conn.execute('DELETE FROM data_lineage WHERE source_object_id = ANY(\$1)', object_ids)
            # Delete objects
            await conn.execute('DELETE FROM minio_objects WHERE object_id = ANY(\$1)', object_ids)
            print(f'✓ Deleted {len(old_objects)} minio_objects and related data_lineage records')
    
    await conn.close()

async def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=${DAYS})
    print(f'Retention cutoff: {cutoff} (older will be deleted)')
    
    dry_run = '${DRY_RUN}' == '--dry-run'
    await cleanup_db(cutoff, dry_run=dry_run)
    print('✓ Retention policy complete')

asyncio.run(main())
"

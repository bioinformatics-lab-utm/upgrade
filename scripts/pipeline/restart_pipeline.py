#!/usr/bin/env python3
"""
Restart a failed pipeline by re-enqueuing it to RQ
"""
import sys
import asyncio
import asyncpg
from redis import Redis
from rq import Queue

sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

from config import config
from tasks.pipeline_tasks import run_nextflow_pipeline


async def restart_pipeline(pipeline_id: int):
    """Restart a failed pipeline"""

    # Get pipeline details from database
    conn = await asyncpg.connect(config.DATABASE_URL)

    row = await conn.fetchrow("""
        SELECT pr.pipeline_id, pr.sample_id, s.sample_code, pr.status
        FROM pipeline_runs pr
        JOIN samples s ON s.sample_id = pr.sample_id
        WHERE pr.pipeline_id = $1
    """, pipeline_id)

    if not row:
        print(f"❌ Pipeline {pipeline_id} not found")
        await conn.close()
        return False

    sample_code = row['sample_code']
    current_status = row['status']

    print(f"📋 Pipeline {pipeline_id}: {sample_code}")
    print(f"   Current status: {current_status}")

    # Reset status to pending
    await conn.execute("""
        UPDATE pipeline_runs
        SET status = 'pending',
            error_message = NULL
        WHERE pipeline_id = $1
    """, pipeline_id)

    # Track restart
    import json
    await conn.execute("""
        INSERT INTO pipeline_progress_events
        (pipeline_id, stage, step, status, details)
        VALUES ($1, 'restart', 'manual_restart', 'started', $2::jsonb)
    """, pipeline_id, json.dumps({'restarted_from': current_status}))

    await conn.close()

    # Enqueue to RQ
    redis_conn = Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        db=0
    )
    queue = Queue('pipeline-queue', connection=redis_conn)

    # Prepare parameters
    input_dir = f"genomic-bronze/{sample_code}/raw/"
    output_dir = f"/results/{sample_code}"

    job = queue.enqueue(
        run_nextflow_pipeline,
        input_dir=input_dir,
        output_dir=output_dir,
        params={},
        pipeline_id=pipeline_id,
        sample_code=sample_code,
        job_timeout=7200  # 2 hours
    )

    print(f"✅ Pipeline re-enqueued")
    print(f"   Job ID: {job.id}")
    print(f"   Input: {input_dir}")
    print(f"   Output: {output_dir}")
    print(f"\n💡 Monitor progress:")
    print(f"   docker logs upgrade_rq_worker -f")

    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 restart_pipeline.py <pipeline_id>")
        print("\nExample:")
        print("  python3 restart_pipeline.py 47")
        sys.exit(1)

    pipeline_id = int(sys.argv[1])

    success = asyncio.run(restart_pipeline(pipeline_id))
    sys.exit(0 if success else 1)

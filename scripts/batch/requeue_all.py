#!/usr/bin/env python3
"""
Re-queue ALL non-completed pipeline runs (queued/pending/failed/running).
Clears stale Redis jobs and creates fresh RQ jobs for all samples.
"""

import sys
import os
import asyncio
import asyncpg
import logging
import signal

sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

POSTGRES_HOST = os.getenv('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5433))
POSTGRES_DB   = os.getenv('POSTGRES_DB', 'upgrade_db')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'upgrade')
POSTGRES_PASS = os.getenv('POSTGRES_PASSWORD', 'upgrade_password')

REDIS_HOST    = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT    = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASS    = os.getenv('REDIS_PASSWORD', 'redis123')


def kill_stuck_processes():
    """Kill any stuck BWA/Nextflow processes from the running pipeline."""
    import subprocess
    result = subprocess.run(['pgrep', '-f', 'bwa mem'], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    killed = 0
    for pid in pids:
        if pid.strip():
            try:
                os.kill(int(pid.strip()), signal.SIGTERM)
                logger.info(f"Killed BWA process PID {pid.strip()}")
                killed += 1
            except Exception as e:
                logger.warning(f"Could not kill PID {pid.strip()}: {e}")

    result = subprocess.run(['pgrep', '-f', 'nextflow.*main.nf'], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    for pid in pids:
        if pid.strip():
            try:
                os.kill(int(pid.strip()), signal.SIGTERM)
                logger.info(f"Killed Nextflow process PID {pid.strip()}")
                killed += 1
            except Exception as e:
                logger.warning(f"Could not kill PID {pid.strip()}: {e}")

    return killed


def clear_redis_queue():
    """Delete the stale pipeline queue in Redis."""
    import redis
    r = redis.Redis(host='127.0.0.1', port=6380, password=REDIS_PASS, decode_responses=True)
    # Note: redis is on external port 6380 when connecting from host
    try:
        queue_len = r.llen('rq:queue:pipeline-queue')
        r.delete('rq:queue:pipeline-queue')
        r.delete('rq:queue:default')
        logger.info(f"Cleared Redis queue ({queue_len} old jobs removed)")
        return queue_len
    except Exception as e:
        logger.warning(f"Could not clear Redis queue: {e}")
        return 0


async def requeue_all():
    conn = await asyncpg.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        database=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASS
    )

    # Get all non-completed pipeline runs
    rows = await conn.fetch("""
        SELECT pr.pipeline_id, pr.sample_id, s.sample_code, pr.status
        FROM pipeline_runs pr
        JOIN samples s ON s.sample_id = pr.sample_id
        WHERE pr.status IN ('queued', 'pending', 'failed', 'running')
        ORDER BY pr.pipeline_id
    """)

    logger.info(f"Found {len(rows)} pipelines to re-queue")
    from collections import Counter
    status_counts = Counter(r['status'] for r in rows)
    logger.info(f"Status breakdown: {dict(status_counts)}")

    # Reset all to pending in DB
    pipeline_ids = [r['pipeline_id'] for r in rows]
    await conn.execute("""
        UPDATE pipeline_runs
        SET status = 'pending',
            error_message = NULL,
            job_id = NULL,
            started_at = NULL,
            completed_at = NULL,
            updated_at = NOW()
        WHERE pipeline_id = ANY($1::int[])
    """, pipeline_ids)
    logger.info(f"Reset {len(pipeline_ids)} pipelines to 'pending' in DB")

    from tasks.pipeline_tasks import enqueue_pipeline

    success = 0
    errors = 0

    for row in rows:
        pipeline_id = row['pipeline_id']
        sample_id   = row['sample_id']
        sample_code = row['sample_code']
        bronze_path = f"genomic-bronze/{sample_code}/raw/"

        try:
            job = enqueue_pipeline(
                pipeline_id=pipeline_id,
                sample_code=sample_code,
                input_dir=bronze_path,
                output_dir=f"/results/{sample_code}",
                params={}
            )

            await conn.execute("""
                UPDATE pipeline_runs
                SET job_id = $1, status = 'queued', updated_at = NOW()
                WHERE pipeline_id = $2
            """, job.id, pipeline_id)

            success += 1
            if success % 50 == 0:
                logger.info(f"Progress: {success}/{len(rows)} queued...")

        except Exception as e:
            errors += 1
            logger.error(f"Failed to re-queue pipeline {pipeline_id} ({sample_code}): {e}")

    await conn.close()
    logger.info(f"\n{'='*50}")
    logger.info(f"DONE: {success}/{len(rows)} queued, {errors} errors")
    logger.info(f"{'='*50}")


if __name__ == '__main__':
    logger.info("Step 1: Killing stuck processes...")
    killed = kill_stuck_processes()
    logger.info(f"  Killed {killed} processes")

    logger.info("Step 2: Clearing stale Redis queue...")
    cleared = clear_redis_queue()

    logger.info("Step 3: Resetting DB and re-queuing all pipelines...")
    asyncio.run(requeue_all())

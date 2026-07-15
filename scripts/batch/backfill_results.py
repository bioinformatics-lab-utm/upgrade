#!/usr/bin/env python3
"""Backfill results for completed pipelines that have no parsed results yet."""

import sys, os, asyncio, logging

sys.path.insert(0, '/home/nicolaedrabcinski/upgrade/web-dashboard/backend')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

import asyncpg
from pathlib import Path


async def backfill():
    from config import config
    from tasks.pipeline_tasks import PipelineExecutor

    conn = await asyncpg.connect(config.DATABASE_URL)
    rows = await conn.fetch("""
        SELECT pr.pipeline_id, pr.sample_id, s.sample_code
        FROM pipeline_runs pr
        JOIN samples s ON s.sample_id = pr.sample_id
        WHERE pr.status = 'completed'
          AND pr.results_parsed_at IS NULL
        ORDER BY pr.pipeline_id
    """)
    await conn.close()

    logger.info(f"Found {len(rows)} completed pipelines without parsed results")

    executor = PipelineExecutor.__new__(PipelineExecutor)
    ok = 0
    failed = 0

    for i, row in enumerate(rows, 1):
        pipeline_id = row['pipeline_id']
        sample_code = row['sample_code']
        output_dir  = Path(f"/results/{sample_code}")

        try:
            await executor._store_pipeline_results(pipeline_id, output_dir, sample_code)
            ok += 1
            logger.info(f"[{i}/{len(rows)}] Parsed pipeline {pipeline_id} ({sample_code})")
        except Exception as e:
            failed += 1
            logger.error(f"[{i}/{len(rows)}] Failed pipeline {pipeline_id} ({sample_code}): {e}")

    logger.info(f"\nDone: {ok} parsed, {failed} errors")


if __name__ == '__main__':
    asyncio.run(backfill())

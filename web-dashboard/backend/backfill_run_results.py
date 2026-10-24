"""
Rebuild resistance_genes and detected_organisms of finished runs from their
Nextflow outputs in MinIO Silver, with the code the results page uses
(services/run_results.py). Fixes rows written by older code:
  - detected_organisms held Kraken2's root nodes ("root", "unclassified",
    "cellular organisms") instead of organisms, which the map counted as pathogens
  - resistance_genes kept only 20 genes per run and repeated genes hit twice

Runs whose Silver files are gone keep their rows, minus the Kraken2 root nodes.

Usage (inside the backend container):
    python backfill_run_results.py [--dry-run] [--pipeline-id N ...]
"""
import argparse
import asyncio
import logging
import time

import asyncpg

from config import config
from minio_helper import get_minio_client
from services.run_results import SILVER, run_amr, run_taxonomy, store_run_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('backfill_run_results')

NOT_ORGANISMS = ('root', 'unclassified', 'cellular organisms')


def has_silver(minio, prefix: str) -> bool:
    return any(True for _ in minio.list_objects(SILVER, prefix=prefix, recursive=True))


async def main(dry_run: bool, pipeline_ids):
    minio = get_minio_client().client
    conn = await asyncpg.connect(
        host=config.POSTGRES_HOST, port=config.POSTGRES_PORT, database=config.POSTGRES_DB,
        user=config.POSTGRES_USER, password=config.POSTGRES_PASSWORD,
    )
    try:
        runs = await conn.fetch(
            """
            SELECT pr.pipeline_id, pr.sample_id, COALESCE(NULLIF(pr.sample_name, ''), s.sample_code) AS name
            FROM pipeline_runs pr JOIN samples s USING (sample_id)
            WHERE pr.status = 'completed' AND ($1::int[] IS NULL OR pr.pipeline_id = ANY($1::int[]))
            ORDER BY pr.pipeline_id
            """,
            pipeline_ids or None
        )
        rebuilt = skipped = failed = 0
        started = time.monotonic()
        for i, run in enumerate(runs, 1):
            prefix = f"{run['name']}/{run['pipeline_id']}/"
            try:
                if not await asyncio.to_thread(has_silver, minio, prefix):
                    if not dry_run:
                        await conn.execute(
                            "DELETE FROM detected_organisms WHERE pipeline_run_id = $1 AND organism_name = ANY($2::text[])",
                            run['pipeline_id'], list(NOT_ORGANISMS)
                        )
                    skipped += 1
                    continue
                if dry_run:
                    amr = await asyncio.to_thread(run_amr, minio, prefix)
                    tax = await asyncio.to_thread(run_taxonomy, minio, prefix)
                    logger.info(f"[dry-run] {run['pipeline_id']}: {amr['total_genes']} genes, "
                                f"{len(tax['organisms'])} genera ({tax['abundance_basis']})")
                else:
                    stored = await store_run_results(conn, minio, run['sample_id'], run['pipeline_id'], prefix)
                    if stored['genes'] or stored['organisms']:
                        logger.info(f"{run['pipeline_id']}: {stored['genes']} genes, {stored['organisms']} genera")
                rebuilt += 1
            except Exception as e:
                failed += 1
                logger.error(f"{run['pipeline_id']}: {e}")
            if i % 100 == 0:
                logger.info(f"... {i}/{len(runs)} runs ({time.monotonic() - started:.0f}s)")
        logger.info(f"Done: {rebuilt} rebuilt, {skipped} without Silver files, {failed} failed")
    finally:
        await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--pipeline-id', type=int, nargs='*')
    args = parser.parse_args()
    asyncio.run(main(args.dry_run, args.pipeline_id))

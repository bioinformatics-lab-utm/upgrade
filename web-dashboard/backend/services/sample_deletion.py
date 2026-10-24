"""
Delete a sample and everything derived from it.

Database: deleting the samples row cascades to its pipeline runs and their
results (resistance genes, organisms, assemblies, QC, progress events,
artifacts, notifications). minio_objects / data_lineage / nextflow_executions
do not cascade and are removed explicitly.

Object storage: every layer keys a sample's files under "<sample_code>/"
(bronze <code>/raw/, silver <code>/<pipeline_id>/, gold <code>/...). Gold
objects are not linked to the sample in minio_objects, so the prefix is what
finds them. Sample codes are unique across all users (SampleService refuses
duplicates), and a prefix is skipped if another sample uses it anyway.

The database is cleaned in one transaction first; files are removed afterwards,
best effort, so a storage hiccup never leaves a half-deleted sample in the UI.
"""
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Dict, List

from config import config

logger = logging.getLogger(__name__)

STORAGE_BUCKETS = ('genomic-bronze', 'genomic-silver', 'genomic-gold')


class SampleNotFound(Exception):
    pass


class SampleHasActiveRuns(Exception):
    def __init__(self, pipeline_ids: List[int]):
        super().__init__(f"Sample has queued/running pipelines: {pipeline_ids}")
        self.pipeline_ids = pipeline_ids


async def delete_sample_records(conn, user_id: int, sample_id: int) -> Dict:
    """
    Remove the sample's rows. Returns what the storage cleanup needs:
        {'sample_code', 'prefixes', 'object_keys': [(bucket, key)], 'local_dirs', 'runs'}

    Raises:
        SampleNotFound: no such sample owned by the user
        SampleHasActiveRuns: a run is queued or running (stop it first)
    """
    async with conn.transaction():
        sample = await conn.fetchrow(
            "SELECT sample_id, sample_code FROM samples WHERE sample_id = $1 AND owner_id = $2 FOR UPDATE",
            sample_id, user_id
        )
        if not sample:
            raise SampleNotFound()

        runs = await conn.fetch(
            """
            SELECT pipeline_id, status, sample_name, results_path, nextflow_execution_id
            FROM pipeline_runs WHERE sample_id = $1
            """,
            sample_id
        )
        active = [r['pipeline_id'] for r in runs if r['status'] in ('queued', 'running')]
        if active:
            raise SampleHasActiveRuns(active)

        pipeline_ids = [r['pipeline_id'] for r in runs]
        candidates = {sample['sample_code']} | {r['sample_name'] for r in runs if r['sample_name']}
        shared = await conn.fetch(
            "SELECT sample_code FROM samples WHERE sample_code = ANY($1::text[]) AND sample_id <> $2",
            list(candidates), sample_id
        )
        prefixes = sorted(candidates - {r['sample_code'] for r in shared})

        objects = await conn.fetch(
            """
            SELECT o.object_id, b.bucket_name, o.object_key, o.execution_id
            FROM minio_objects o
            JOIN minio_buckets b ON b.bucket_id = o.bucket_id
            WHERE o.sample_id = $1
               OR o.pipeline_id = ANY($2::int[])
               OR (b.bucket_name = ANY($3::text[]) AND split_part(o.object_key, '/', 1) = ANY($4::text[]))
            """,
            sample_id, pipeline_ids, list(STORAGE_BUCKETS), prefixes
        )
        object_ids = [o['object_id'] for o in objects]

        await conn.execute(
            "DELETE FROM data_lineage WHERE source_object_id = ANY($1::int[]) OR target_object_id = ANY($1::int[])",
            object_ids
        )
        await conn.execute("DELETE FROM minio_objects WHERE object_id = ANY($1::int[])", object_ids)
        await conn.execute("DELETE FROM samples WHERE sample_id = $1", sample_id)

        # The worker links its nextflow_executions row to a run only by name
        # ("rq_job_<job id>_<sample code>", see PipelineExecutor.create_nextflow_execution)
        # and through the files it uploaded; a rerun gets a new job id, so match any.
        named = await conn.fetch(
            "SELECT execution_id FROM nextflow_executions WHERE execution_name ~ ANY($1::text[])",
            [f'^rq_job_[0-9a-f-]{{36}}_{prefix}$' for prefix in prefixes]
        ) if prefixes else []
        execution_ids = sorted(
            {r['nextflow_execution_id'] for r in runs if r['nextflow_execution_id']}
            | {o['execution_id'] for o in objects if o['execution_id']}
            | {r['execution_id'] for r in named}
        )
        if execution_ids:
            await conn.execute(
                """
                DELETE FROM nextflow_executions e
                WHERE e.execution_id = ANY($1::int[])
                  AND NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.nextflow_execution_id = e.execution_id)
                  AND NOT EXISTS (SELECT 1 FROM minio_objects o WHERE o.execution_id = e.execution_id)
                """,
                execution_ids
            )

    local_dirs = _local_dirs(runs, prefixes)
    logger.info(
        f"Deleted sample {sample['sample_code']} (ID: {sample_id}) of user {user_id}: "
        f"{len(runs)} run(s), {len(object_ids)} object record(s)"
    )
    return {
        'sample_code': sample['sample_code'],
        'prefixes': prefixes,
        'object_keys': [(o['bucket_name'], o['object_key']) for o in objects],
        'local_dirs': local_dirs,
        'runs': len(runs),
    }


def _local_dirs(runs, prefixes) -> List[Path]:
    """Results and input dirs on disk, only inside the results / work dirs."""
    dirs = set()
    results_root = config.RESULTS_DIR.resolve()
    for run in runs:
        if run['results_path']:
            path = Path(run['results_path']).resolve()
            if path.parent == results_root and path.name in prefixes:
                dirs.add(path)
    for prefix in prefixes:
        dirs.add(config.RESULTS_DIR / prefix)
        dirs.add(config.WORK_DIR / prefix)  # downloaded input FASTQ
    return sorted(dirs)


def remove_sample_files(minio_client, cleanup: Dict) -> Dict:
    """Blocking: delete the sample's objects and local dirs. Returns counts and errors."""
    from minio.deleteobjects import DeleteObject

    errors: List[str] = []
    keys = {(bucket, key) for bucket, key in cleanup['object_keys']}
    for bucket in STORAGE_BUCKETS:
        for prefix in cleanup['prefixes']:
            try:
                for obj in minio_client.list_objects(bucket, prefix=f"{prefix}/", recursive=True):
                    keys.add((bucket, obj.object_name))
            except Exception as e:
                errors.append(f"list {bucket}/{prefix}/: {e}")

    removed = 0
    by_bucket: Dict[str, List[str]] = {}
    for bucket, key in keys:
        by_bucket.setdefault(bucket, []).append(key)
    for bucket, bucket_keys in by_bucket.items():
        try:
            failures = list(minio_client.remove_objects(bucket, [DeleteObject(k) for k in bucket_keys]))
            errors.extend(f"{bucket}/{f.name}: {f.message}" for f in failures)
            removed += len(bucket_keys) - len(failures)
        except Exception as e:
            errors.append(f"remove from {bucket}: {e}")

    for path in cleanup['local_dirs']:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            if path.exists():
                errors.append(f"could not remove {path}")

    if errors:
        logger.warning(f"Sample {cleanup['sample_code']}: storage cleanup incomplete: {errors[:5]}")
    return {'objects_removed': removed, 'errors': errors}


async def delete_sample(pool, minio_client, user_id: int, sample_id: int) -> Dict:
    async with pool.acquire() as conn:
        cleanup = await delete_sample_records(conn, user_id, sample_id)
    storage = await asyncio.to_thread(remove_sample_files, minio_client, cleanup)
    return {
        'sample_code': cleanup['sample_code'],
        'runs_deleted': cleanup['runs'],
        'objects_removed': storage['objects_removed'],
        'storage_errors': len(storage['errors']),
    }

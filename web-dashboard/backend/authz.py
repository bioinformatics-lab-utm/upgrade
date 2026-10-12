"""
Per-user data ownership.

A sample belongs to samples.owner_id; pipeline runs and every result derived from
them belong to the owner of their sample. Handlers call these helpers with the
authenticated user (request.ctx.user['user_id']) and answer 404 when the user does
not own the resource, so other users' data is neither shown nor confirmed to exist.
"""
from typing import Optional


def current_user_id(request) -> int:
    return request.ctx.user['user_id']


async def user_owns_sample(conn, user_id: int, sample_id: int) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM samples WHERE sample_id = $1 AND owner_id = $2)",
        sample_id, user_id
    )


async def user_owns_pipeline(conn, user_id: int, pipeline_id: int) -> bool:
    return await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE pr.pipeline_id = $1 AND s.owner_id = $2
        )
        """,
        pipeline_id, user_id
    )


async def get_owned_pipeline_by_job(conn, user_id: int, job_id: str):
    """Pipeline run (pipeline_id, status) for an RQ job id, if the user owns it."""
    return await conn.fetchrow(
        """
        SELECT pr.pipeline_id, pr.status
        FROM pipeline_runs pr
        JOIN samples s ON s.sample_id = pr.sample_id
        WHERE pr.job_id = $1 AND s.owner_id = $2
        """,
        job_id, user_id
    )


async def user_owns_run_ref(conn, user_id: int, run_ref: str) -> bool:
    """
    Results endpoints address a run either by pipeline_id or by its results
    directory name (sample code / sample_name / basename of results_path).
    """
    pipeline_id: Optional[int] = int(run_ref) if run_ref.isdigit() else None
    return await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE s.owner_id = $1
              AND (
                    pr.pipeline_id = $2
                 OR pr.sample_name = $3
                 OR s.sample_code = $3
                 OR regexp_replace(COALESCE(pr.results_path, ''), '^.*/', '') = $3
              )
        )
        """,
        user_id, pipeline_id, run_ref
    )

"""
API endpoints for real-time pipeline monitoring
"""
from sanic import Blueprint
from sanic.response import json
from sanic.exceptions import NotFound, ServerError
from pathlib import Path
from datetime import timezone
from typing import Optional, List, Dict
import asyncio
import io
import re

import logging

from auth import protected
from authz import current_user_id
from config import config
from minio_helper import get_minio_client
from services.nextflow_progress import find_run_log, parse_run_log, build_live_status, process_name
from utils.timestamps import to_iso

logger = logging.getLogger(__name__)

monitoring_bp = Blueprint('monitoring', url_prefix='/api/monitoring')


def _parse_trace_lines(lines) -> List[Dict]:
    """Parse trace lines into task dicts."""
    tasks = []
    if len(lines) < 2:
        return tasks
    header = lines[0].strip().split('\t')
    for line in lines[1:]:
        fields = line.strip().split('\t')
        if len(fields) != len(header):
            continue
        task_data = dict(zip(header, fields))
        tasks.append({
            'task_id': task_data.get('task_id', ''),
            'name': task_data.get('name', ''),
            'status': task_data.get('status', ''),
            'exit': task_data.get('exit', ''),
            'submit': task_data.get('submit', ''),
            'start': task_data.get('start', ''),
            'complete': task_data.get('complete', ''),
            'duration': task_data.get('duration', ''),
            'realtime': task_data.get('realtime', ''),
            '%cpu': task_data.get('%cpu', ''),
            '%mem': task_data.get('%mem', ''),
            'rss': task_data.get('rss', ''),
            'vmem': task_data.get('vmem', ''),
            'peak_rss': task_data.get('peak_rss', ''),
            'peak_vmem': task_data.get('peak_vmem', ''),
            'rchar': task_data.get('rchar', ''),
            'wchar': task_data.get('wchar', ''),
        })
    return tasks


def _fetch_trace_from_minio(sample_name: str, pipeline_id: int) -> List[Dict]:
    """Download nextflow_trace.txt from MinIO Silver and parse it."""
    try:
        minio = get_minio_client()
        obj_key = f"{sample_name}/{pipeline_id}/nextflow_trace.txt"
        response = minio.client.get_object('genomic-silver', obj_key)
        content = response.read().decode('utf-8')
        response.close()
        return _parse_trace_lines(content.splitlines(keepends=True))
    except Exception as e:
        logger.warning(f"Failed to fetch trace from MinIO for {sample_name}/{pipeline_id}: {e}")
        return []


def parse_nextflow_trace(trace_file: Path) -> List[Dict]:
    """Parse Nextflow trace.txt file to extract task information"""
    if not trace_file.exists():
        return []

    try:
        with open(trace_file, 'r') as f:
            lines = f.readlines()
        tasks = _parse_trace_lines(lines)
    except Exception as e:
        logger.error(f"Error parsing trace file: {e}")
        return []
    
    return tasks


# Process names a finished run actually executed, keyed by that run's pipeline_id
_reference_processes: Dict[int, set] = {}


async def _expected_processes(conn, pipeline_id: int, pipeline_name: str) -> Optional[set]:
    """
    Processes the latest successful run of the same pipeline executed, as the best
    guess of what this run still has to do (the workflow declares more processes
    than any one run uses). None when there is no such run to compare with.
    """
    ref = await conn.fetchrow("""
        SELECT pipeline_id, sample_name, results_path
        FROM pipeline_runs
        WHERE status = 'completed' AND pipeline_name = $1 AND pipeline_id <> $2
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    """, pipeline_name, pipeline_id)
    if not ref:
        return None
    if ref['pipeline_id'] not in _reference_processes:
        trace = Path(ref['results_path'] or '') / 'nextflow_trace.txt'
        if ref['results_path'] and trace.exists():
            tasks = parse_nextflow_trace(trace)
        else:
            tasks = await asyncio.to_thread(_fetch_trace_from_minio, ref['sample_name'], ref['pipeline_id'])
        if not tasks:
            return None
        _reference_processes.clear()
        _reference_processes[ref['pipeline_id']] = {process_name(t['name']) for t in tasks}
    return _reference_processes[ref['pipeline_id']]


def _trace_since(trace_file: Path, started_at) -> List[Dict]:
    """Trace rows of the current run only (a rerun writes to the same results dir)."""
    try:
        if started_at is not None:
            started = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
            if trace_file.stat().st_mtime < started.timestamp():
                return []
    except OSError:
        return []
    return parse_nextflow_trace(trace_file)


@monitoring_bp.get("/pipeline/<pipeline_id:int>/status")
@protected
async def get_pipeline_status(request, pipeline_id: int):
    """
    Detailed real-time status of a pipeline run.

    While the run is queued or running, progress comes from Nextflow's live log
    (see services/nextflow_progress.py); once it has finished, from its trace.

    Response (abridged):
        {
            "pipeline_id": 1725, "status": "running",
            "phase": "queued" | "preparing" | "running" | "completed" | "failed" | "cancelled",
            "started_at": "...+00:00", "completed_at": null,
            "summary": {"total": 14, "completed": 5, "cached": 0, "running": 1,
                        "pending": 8, "failed": 0, "aborted": 0},
            "progress": 35,
            "processes": [{"name": "FLYE", "count": 1, "completed": 0, "running": 1,
                           "failed": 0, "aborted": 0, "pending": false}, ...],
            "tasks": [...]
        }
    """
    db_pool = request.app.ctx.db_pool
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT pr.sample_name, pr.results_path, pr.status, pr.pipeline_name,
                   pr.started_at, pr.completed_at, pr.error_message
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE pr.pipeline_id = $1 AND s.owner_id = $2
        """, pipeline_id, current_user_id(request))

        if not row:
            raise NotFound(f"Pipeline {pipeline_id} not found")

        pipeline_status = row['status']
        in_progress = pipeline_status in ('queued', 'running')
        expected = (
            await _expected_processes(conn, pipeline_id, row['pipeline_name'])
            if in_progress or pipeline_status == 'cancelled' else None
        )

    sample_name = row['sample_name']
    results_path = row['results_path']
    result_dir = Path(results_path) if results_path else None
    if result_dir is not None and not result_dir.exists():
        result_dir = None
    if result_dir is None and sample_name and (config.RESULTS_DIR / sample_name).exists():
        result_dir = config.RESULTS_DIR / sample_name
    trace_file = result_dir / "nextflow_trace.txt" if result_dir else None

    parsed = {}
    phase = pipeline_status
    if in_progress:
        trace_tasks = _trace_since(trace_file, row['started_at']) if trace_file and trace_file.exists() else []
        log = find_run_log(config.WORK_DIR, results_path, row['started_at']) if pipeline_status == 'running' else None
        if log:
            with open(log, 'r', errors='replace') as f:
                parsed = parse_run_log(f)
        if pipeline_status == 'running':
            phase = 'running' if log else 'preparing'
    elif trace_file and trace_file.exists():
        trace_tasks = parse_nextflow_trace(trace_file)
        if pipeline_status == 'cancelled':
            # The trace has no row for the tasks that were stopped; the log (kept
            # until the next run starts) does
            log = find_run_log(config.WORK_DIR, results_path, row['started_at'])
            if log:
                with open(log, 'r', errors='replace') as f:
                    parsed = parse_run_log(f)
    else:
        # Results are cleaned up after a successful run; the trace lives on in MinIO Silver
        trace_tasks = await asyncio.to_thread(_fetch_trace_from_minio, sample_name, pipeline_id)

    live = build_live_status(parsed, trace_tasks, expected, pipeline_status)

    return json({
        'pipeline_id': pipeline_id,
        'sample_name': sample_name,
        'status': pipeline_status,
        'db_status': pipeline_status,
        'phase': phase,
        'started_at': to_iso(row['started_at']),
        'completed_at': to_iso(row['completed_at']),
        'error_message': row['error_message'] if pipeline_status in ('failed', 'cancelled') else None,
        'result_dir': str(result_dir) if result_dir else 'minio',
        **live,
    })


@monitoring_bp.get("/pipeline/<pipeline_id:int>/log")
@protected
async def get_pipeline_log(request, pipeline_id: int):
    """Get pipeline log file content"""

    lines = int(request.args.get('lines', 100))
    log_type = request.args.get('log_type', 'nextflow')  # nextflow, stdout, stderr

    # Resolve result dir via DB
    db_pool = request.app.ctx.db_pool
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pr.log_file_path, pr.results_path, pr.sample_name, pr.status, pr.started_at
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE pr.pipeline_id = $1 AND s.owner_id = $2
            """,
            pipeline_id, current_user_id(request)
        )

    if not row:
        raise NotFound(f"Pipeline {pipeline_id} not found")

    results_path = row['results_path']
    result_dir = Path(results_path) if results_path else None

    # Map log_type to actual file
    if log_type == "nextflow":
        # Prefer our written execution log; fall back to Nextflow's internal log
        candidates = []
        if result_dir:
            candidates = [
                result_dir / "nextflow_execution.log",
                result_dir / ".nextflow.log",
            ]
        if row['log_file_path']:
            candidates.insert(0, Path(row['log_file_path']))
        if row['status'] == 'running':
            # The execution log is only written once Nextflow exits; follow its live log meanwhile
            live_log = find_run_log(config.WORK_DIR, results_path, row['started_at'])
            candidates = [live_log] if live_log else []
        log_file = next((p for p in candidates if p.exists()), None)
    elif log_type == "stdout":
        log_file = (result_dir / "nextflow_report.html") if result_dir else None
    elif log_type == "stderr":
        log_file = (result_dir / "nextflow_trace.txt") if result_dir else None
    else:
        return json({'error': 'Invalid log_type'}, status=400)

    if (not log_file or not log_file.exists()) and row['status'] in ('queued', 'running'):
        waiting_for = 'a free worker' if row['status'] == 'queued' else 'the input files to download'
        return json({
            'content': f"Nextflow has not started yet - waiting for {waiting_for}.",
            'lines': 0,
            'file': ''
        })

    if not log_file or not log_file.exists():
        # Try MinIO Silver for the execution log
        sample_name = row['sample_name']
        minio_content = None
        try:
            minio = get_minio_client()
            obj_key = f"{sample_name}/{pipeline_id}/nextflow_execution.log"
            resp = minio.client.get_object('genomic-silver', obj_key)
            minio_content = resp.read().decode('utf-8', errors='replace')
            resp.close()
        except Exception as e:
            logger.debug(f"Execution log not in MinIO for {sample_name}/{pipeline_id}: {e}")
        if minio_content:
            all_lines = minio_content.splitlines(keepends=True)
            selected = all_lines[-lines:] if lines else all_lines
            return json({'content': ''.join(selected), 'lines': len(selected),
                         'total_lines': len(all_lines), 'file': f'minio:genomic-silver/{sample_name}/{pipeline_id}/nextflow_execution.log'})
        return json({
            'content': f"Log not available for pipeline {pipeline_id} (results cleaned up after completion).",
            'lines': 0,
            'file': str(log_file) if log_file else ''
        })

    try:
        with open(log_file, 'r', errors='replace') as f:
            all_lines = f.readlines()
            selected_lines = all_lines[-lines:] if lines else all_lines
            content = ''.join(selected_lines)

        return json({
            'content': content,
            'lines': len(selected_lines),
            'total_lines': len(all_lines),
            'file': str(log_file)
        })
    except Exception as e:
        raise ServerError(f"Error reading log: {str(e)}")


@monitoring_bp.get("/pipeline/<pipeline_id:int>/report")
@protected
async def get_pipeline_report(request, pipeline_id: int):
    """Get generated HTML report"""

    db_pool = request.app.ctx.db_pool
    async with db_pool.acquire() as conn:
        results_path = await conn.fetchval(
            """
            SELECT pr.results_path
            FROM pipeline_runs pr
            JOIN samples s ON s.sample_id = pr.sample_id
            WHERE pr.pipeline_id = $1 AND s.owner_id = $2
            """,
            pipeline_id, current_user_id(request)
        )

    if not results_path:
        raise NotFound("Pipeline report not found")

    report_file = config.RESULTS_DIR / Path(results_path).name / "nextflow_report.html"
    if not report_file.exists():
        raise NotFound("Report file not found")
    
    with open(report_file, 'r') as f:
        content = f.read()
    
    return json({
        'html': content,
        'file': str(report_file)
    })

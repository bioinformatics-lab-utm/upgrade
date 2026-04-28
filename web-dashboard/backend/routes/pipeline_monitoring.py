"""
API endpoints for real-time pipeline monitoring
"""
from sanic import Blueprint
from sanic.response import json
from sanic.exceptions import NotFound, ServerError
from pathlib import Path
from typing import Optional, List, Dict
import io
import re

import logging

from auth import protected
from config import config
from minio_helper import get_minio_client

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


def get_process_summary(tasks: List[Dict]) -> Dict:
    """Generate summary statistics from tasks"""
    if not tasks:
        return {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'running': 0,
            'cached': 0,
            'pending': 0
        }
    
    summary = {
        'total': len(tasks),
        'completed': sum(1 for t in tasks if t['status'] == 'COMPLETED'),
        'failed': sum(1 for t in tasks if t['status'] == 'FAILED'),
        'running': sum(1 for t in tasks if t['status'] == 'RUNNING'),
        'cached': sum(1 for t in tasks if t['status'] == 'CACHED'),
        'pending': sum(1 for t in tasks if t['status'] in ['SUBMITTED', 'PENDING']),
        'aborted': sum(1 for t in tasks if t['status'] == 'ABORTED')
    }
    
    return summary


def get_process_groups(tasks: List[Dict]) -> Dict[str, List[Dict]]:
    """Group tasks by process name"""
    groups = {}
    for task in tasks:
        # Extract process name (e.g., "NANOPLOT (sample1)" -> "NANOPLOT")
        name = task['name']
        process_name = re.sub(r'\s*\(.*\)$', '', name).strip()
        
        if process_name not in groups:
            groups[process_name] = []
        groups[process_name].append(task)
    
    return groups


@monitoring_bp.get("/pipeline/<pipeline_id:int>/status")
@protected
async def get_pipeline_status(request, pipeline_id: int):
    """Get detailed real-time status of a pipeline run"""
    
    # Get sample_name and results_path from pipeline_runs
    db_pool = request.app.ctx.db_pool
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT sample_name, results_path, status 
            FROM pipeline_runs 
            WHERE pipeline_id = $1
        """, pipeline_id)
    
    if not row:
        raise NotFound(f"Pipeline {pipeline_id} not found")
    
    sample_name = row['sample_name']
    results_path = row['results_path']
    pipeline_status = row['status']
    
    # Find result directory
    results_base = config.RESULTS_DIR
    result_dir = None
    
    # Try using results_path from DB
    if results_path:
        result_dir = Path(results_path)
        if not result_dir.exists():
            result_dir = None
    
    # Fallback: search by sample_name
    if not result_dir and sample_name:
        potential_dir = results_base / sample_name
        if potential_dir.exists():
            result_dir = potential_dir
    
    # Last resort: search all directories for matching trace
    if not result_dir:
        for d in results_base.glob("*/"):
            if d.is_dir() and d.name == sample_name:
                result_dir = d
                break
    
    # Parse trace - from disk if available, else from MinIO Silver (results cleaned up after upload)
    if result_dir and result_dir.exists() and (result_dir / "nextflow_trace.txt").exists():
        tasks = parse_nextflow_trace(result_dir / "nextflow_trace.txt")
    else:
        tasks = _fetch_trace_from_minio(sample_name, pipeline_id)

    if not tasks and pipeline_status not in ('completed', 'failed'):
        return json({
            'pipeline_id': pipeline_id,
            'sample_name': sample_name,
            'status': pipeline_status,
            'error': 'Results directory not found',
            'summary': get_process_summary([]),
            'progress': 0,
            'processes': [],
            'tasks': []
        })
    
    # Get summary
    summary = get_process_summary(tasks)
    
    # Group by process
    process_groups = get_process_groups(tasks)
    
    # Calculate progress percentage
    total = summary['total']
    completed = summary['completed'] + summary['cached']
    progress = int((completed / total * 100)) if total > 0 else 0
    
    return json({
        'pipeline_id': pipeline_id,
        'sample_name': sample_name,
        'result_dir': str(result_dir) if result_dir else 'minio',
        'db_status': pipeline_status,
        'summary': summary,
        'progress': progress,
        'processes': [
            {
                'name': name,
                'tasks': tasks_list,
                'count': len(tasks_list),
                'completed': sum(1 for t in tasks_list if t['status'] in ['COMPLETED', 'CACHED']),
                'failed': sum(1 for t in tasks_list if t['status'] == 'FAILED'),
                'running': sum(1 for t in tasks_list if t['status'] == 'RUNNING'),
            }
            for name, tasks_list in process_groups.items()
        ],
        'tasks': tasks
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
            "SELECT log_file_path, results_path, sample_name FROM pipeline_runs WHERE pipeline_id = $1",
            pipeline_id
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
        log_file = next((p for p in candidates if p.exists()), None)
    elif log_type == "stdout":
        log_file = (result_dir / "nextflow_report.html") if result_dir else None
    elif log_type == "stderr":
        log_file = (result_dir / "nextflow_trace.txt") if result_dir else None
    else:
        return json({'error': 'Invalid log_type'}, status=400)

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
    
    results_base = config.RESULTS_DIR
    result_dir = None
    
    for d in results_base.glob("*/"):
        if d.is_dir():
            report_file = d / "nextflow_report.html"
            if report_file.exists():
                result_dir = d
                break
    
    if not result_dir:
        raise NotFound("Pipeline report not found")
    
    report_file = result_dir / "nextflow_report.html"
    if not report_file.exists():
        raise NotFound("Report file not found")
    
    with open(report_file, 'r') as f:
        content = f.read()
    
    return json({
        'html': content,
        'file': str(report_file)
    })

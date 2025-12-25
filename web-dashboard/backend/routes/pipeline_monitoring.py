"""
API endpoints for real-time pipeline monitoring
"""
from sanic import Blueprint
from sanic.response import json
from sanic.exceptions import NotFound, ServerError
from pathlib import Path
from typing import Optional, List, Dict
import re

from config import config

monitoring_bp = Blueprint('monitoring', url_prefix='/api/monitoring')


def parse_nextflow_trace(trace_file: Path) -> List[Dict]:
    """Parse Nextflow trace.txt file to extract task information"""
    if not trace_file.exists():
        return []
    
    tasks = []
    try:
        with open(trace_file, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                return []
            
            # Parse header
            header = lines[0].strip().split('\t')
            
            # Parse tasks
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
    except Exception as e:
        print(f"Error parsing trace file: {e}")
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
    
    if not result_dir or not result_dir.exists():
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
    
    # Parse trace file
    trace_file = result_dir / "nextflow_trace.txt"
    tasks = parse_nextflow_trace(trace_file)
    
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
        'result_dir': str(result_dir),
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
async def get_pipeline_log(request, pipeline_id: int):
    """Get pipeline log file content"""
    
    lines = int(request.args.get('lines', 100))
    log_type = request.args.get('log_type', 'nextflow')  # nextflow, stdout, stderr
    
    # Find result directory
    results_base = config.RESULTS_DIR
    result_dir = None
    
    for d in results_base.glob("*/"):
        if d.is_dir():
            result_dir = d
            break
    
    if not result_dir:
        raise NotFound("Pipeline results not found")
    
    # Select log file
    if log_type == "nextflow":
        log_file = result_dir / ".nextflow.log"
    elif log_type == "stdout":
        log_file = result_dir / "nextflow.out"
    elif log_type == "stderr":
        log_file = result_dir / "nextflow.err"
    else:
        return json({'error': 'Invalid log_type'}, status=400)
    
    if not log_file.exists():
        return json({
            'content': f"Log file not found: {log_file.name}",
            'lines': 0,
            'file': str(log_file)
        })
    
    # Read last N lines
    try:
        with open(log_file, 'r') as f:
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

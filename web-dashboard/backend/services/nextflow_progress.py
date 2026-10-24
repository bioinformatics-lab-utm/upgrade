"""
Live progress of a running Nextflow pipeline.

nextflow_trace.txt only gets a row when a task *finishes*, so while a run is in
progress it cannot tell what is running or still to come. The worker launches
Nextflow with the work dir as its cwd, so Nextflow's own log
(<WORK_DIR>/.nextflow.log) is written there live and records every step:

    Starting process > FLYE                          process is part of the workflow
    [02/4ea087] Submitted process > FLYE (s1)        task started
    [0d/768c34] Cached process > FILTLONG (s1)       task reused from a previous run
    Task completed > TaskHandler[id: 4; name: FLYE (s1); status: COMPLETED; exit: 0; ...]

Only one Nextflow run can use that launch dir at a time (Nextflow locks it), so
the current log belongs to the running pipeline when its command line has the
pipeline's --outdir.
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_STARTING = re.compile(r'Starting process > (\S+)')
_SUBMITTED = re.compile(r'\[[0-9a-f]{2}/[0-9a-f]{6}\] (?:Re-)?[Ss]ubmitted process > (.+?)\s*$')
_CACHED = re.compile(r'\[[0-9a-f]{2}/[0-9a-f]{6}\] Cached process > (.+?)\s*$')
_COMPLETED = re.compile(r'Task completed > TaskHandler\[id: \d+; name: (.+?); status: (\w+); exit: ([^;]+);')

# Exit codes of tasks Nextflow killed (SIGTERM / SIGKILL) when the run was stopped
_KILLED_EXIT_CODES = {'143', '137', '-'}


def process_name(task_name: str) -> str:
    """'NANOPLOT (sample1)' -> 'NANOPLOT'"""
    return re.sub(r'\s*\(.*\)$', '', task_name).strip()


def find_run_log(launch_dir: Path, results_path: Optional[str], started_at: Optional[datetime]) -> Optional[Path]:
    """
    The .nextflow.log of the run writing to `results_path`, or None if the
    current log belongs to another (older) run, e.g. while the worker is still
    downloading the input files.
    """
    log = launch_dir / '.nextflow.log'
    if not results_path or not log.exists():
        return None
    try:
        if started_at is not None:
            started = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
            if log.stat().st_mtime < started.timestamp():
                return None
        with open(log, 'r', errors='replace') as f:
            first_line = f.readline()
    except OSError:
        return None
    # "$> nextflow run /nextflow/main.nf ... --outdir /results/sample_x -work-dir ..."
    if f'--outdir {results_path.rstrip("/")} ' not in first_line + ' ':
        return None
    return log


def parse_run_log(lines) -> Dict:
    """
    Returns:
        {'processes': [names of the workflow's processes, in start order],
         'tasks': {task name: {'name', 'status', 'exit'}}}   (latest event per task)
    """
    processes: List[str] = []
    tasks: Dict[str, Dict] = {}
    for line in lines:
        if 'process >' in line:
            m = _STARTING.search(line)
            if m:
                if m.group(1) not in processes:
                    processes.append(m.group(1))
                continue
            m = _SUBMITTED.search(line)
            if m:
                tasks[m.group(1)] = {'name': m.group(1), 'status': 'RUNNING', 'exit': ''}
                continue
            m = _CACHED.search(line)
            if m:
                tasks[m.group(1)] = {'name': m.group(1), 'status': 'CACHED', 'exit': '0'}
                continue
        elif 'Task completed >' in line:
            m = _COMPLETED.search(line)
            if m:
                name, status, exit_code = m.group(1), m.group(2), m.group(3).strip()
                ok = status == 'COMPLETED' and exit_code == '0'
                tasks[name] = {'name': name, 'status': 'COMPLETED' if ok else 'FAILED', 'exit': exit_code}
    return {'processes': processes, 'tasks': tasks}


def build_live_status(parsed: Dict, trace_tasks: List[Dict], expected: Optional[set], run_status: str) -> Dict:
    """
    Combine the log with the (partial) trace into the monitor's summary.

    Args:
        parsed: parse_run_log() output; may be empty when the run has not reached Nextflow yet
        trace_tasks: rows of nextflow_trace.txt written so far (finished tasks, with resource usage)
        expected: process names a comparable finished run actually executed; the
            workflow declares more processes than any one run needs, so this keeps
            "pending" to the ones that will most likely run. None = unknown.
        run_status: pipeline_runs.status
    """
    finished = run_status in ('completed', 'failed', 'cancelled')
    by_name = {t['name']: dict(t) for t in trace_tasks}
    for name, task in parsed.get('tasks', {}).items():
        if name in by_name:
            # The trace row is final and has duration/CPU/memory; keep it unless the
            # task has been resubmitted since (a retry)
            if task['status'] == 'RUNNING' and by_name[name]['status'] == 'FAILED':
                by_name[name].update(status='RUNNING')
            continue
        by_name[name] = {'task_id': '', 'name': name, 'status': task['status'], 'exit': task['exit'],
                         'duration': '', '%cpu': '', 'rss': ''}

    tasks = list(by_name.values())
    if run_status == 'cancelled':
        for t in tasks:
            if t['status'] == 'RUNNING' or (t['status'] == 'FAILED' and t.get('exit') in _KILLED_EXIT_CODES):
                t['status'] = 'ABORTED'
    elif finished:
        for t in tasks:
            if t['status'] == 'RUNNING':
                t['status'] = 'ABORTED'

    groups: Dict[str, List[Dict]] = {}
    for t in tasks:
        groups.setdefault(process_name(t['name']), []).append(t)

    # Processes still to come: pending while the run is active; for a stopped run,
    # the ones it never got to (they count against its progress)
    waiting: List[str] = []
    if not finished or run_status == 'cancelled':
        declared = parsed.get('processes') or []
        candidates = [p for p in declared if expected is None or p in expected]
        if not declared and expected:
            # Queued, or still downloading the input: nothing reached Nextflow yet
            candidates = sorted(expected)
        waiting = [p for p in candidates if p not in groups]
    not_started = waiting if finished else []
    if finished:
        waiting = []

    count = lambda *states: sum(1 for t in tasks if t['status'] in states)
    summary = {
        'total': len(tasks) + len(waiting),
        'completed': count('COMPLETED'),
        'cached': count('CACHED'),
        'running': count('RUNNING', 'SUBMITTED'),
        'failed': count('FAILED'),
        'aborted': count('ABORTED'),
        'pending': len(waiting),
        'not_started': len(not_started),
    }
    total_planned = summary['total'] + len(not_started)

    done = summary['completed'] + summary['cached']
    if run_status == 'completed':
        progress = 100
    elif total_planned:
        progress = int(done / total_planned * 100)
        if not finished:
            progress = min(progress, 99)
    else:
        progress = 0

    processes = [
        {
            'name': name,
            'tasks': group,
            'count': len(group),
            'completed': sum(1 for t in group if t['status'] in ('COMPLETED', 'CACHED')),
            'failed': sum(1 for t in group if t['status'] == 'FAILED'),
            'running': sum(1 for t in group if t['status'] in ('RUNNING', 'SUBMITTED')),
            'aborted': sum(1 for t in group if t['status'] == 'ABORTED'),
            'pending': False,
        }
        for name, group in groups.items()
    ] + [
        {'name': name, 'tasks': [], 'count': 0, 'completed': 0, 'failed': 0, 'running': 0,
         'aborted': 0, 'pending': True}
        for name in waiting
    ]

    return {'summary': summary, 'progress': progress, 'processes': processes, 'tasks': tasks}

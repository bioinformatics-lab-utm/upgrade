"""
Tests for live pipeline progress, UTC timestamps and stopping a run
(services/nextflow_progress.py, utils/timestamps.py, routes/pipeline_v2.py cancel,
tasks/pipeline_tasks.py run_nextflow_cancellable)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch

import pytest

LOG = """\
Oct-16 07:56:27.654 [main] DEBUG nextflow.cli.Launcher - $> nextflow run /nextflow/main.nf -profile docker --input_dir /tmp/nf-work/s1/input --outdir /results/s1 -work-dir /tmp/nf-work -resume
Oct-16 07:56:31.723 [main] DEBUG nextflow.processor.TaskProcessor - Starting process > NANOPLOT
Oct-16 07:56:31.724 [main] DEBUG nextflow.processor.TaskProcessor - Starting process > FILTLONG
Oct-16 07:56:31.724 [main] DEBUG nextflow.processor.TaskProcessor - Starting process > FLYE
Oct-16 07:56:31.724 [main] DEBUG nextflow.processor.TaskProcessor - Starting process > SKIP_ASSEMBLY_MARKER
Oct-16 07:56:31.724 [main] DEBUG nextflow.processor.TaskProcessor - Starting process > MEDAKA
Oct-16 07:56:31.882 [Task submitter] INFO  nextflow.Session - [0d/768c34] Submitted process > FILTLONG (s1)
Oct-16 07:56:37.317 [Task monitor] DEBUG n.processor.TaskPollingMonitor - Task completed > TaskHandler[id: 1; name: FILTLONG (s1); status: COMPLETED; exit: 0; error: -; workDir: /tmp/nf-work/0d/768c34]
Oct-16 07:56:37.325 [Task submitter] INFO  nextflow.Session - [db/d1e9c5] Submitted process > NANOPLOT (s1)
Oct-16 07:56:37.400 [Task submitter] INFO  nextflow.Session - [02/4ea087] Submitted process > FLYE (s1)
"""


class TestToIso:
    def test_naive_datetime_is_marked_utc(self):
        """Test naive DB timestamps get an explicit UTC offset"""
        from utils.timestamps import to_iso
        assert to_iso(datetime(2026, 10, 16, 7, 56, 25)) == '2026-10-16T07:56:25+00:00'

    def test_aware_datetime_and_date_unchanged(self):
        from utils.timestamps import to_iso
        from datetime import date
        aware = datetime(2026, 10, 16, 10, 0, tzinfo=timezone(timedelta(hours=3)))
        assert to_iso(aware) == '2026-10-16T10:00:00+03:00'
        assert to_iso(date(2026, 10, 16)) == '2026-10-16'
        assert to_iso(None) is None

    def test_pipeline_api_encoder_uses_utc(self):
        """Test the pipeline API serializes run timestamps with an offset"""
        from routes.pipeline_v2 import json_response
        response = json_response({'started_at': datetime(2026, 10, 16, 7, 56)})
        assert json.loads(response.body)['started_at'] == '2026-10-16T07:56:00+00:00'


class TestParseRunLog:
    def test_tracks_task_states(self):
        from services.nextflow_progress import parse_run_log

        parsed = parse_run_log(LOG.splitlines())

        assert parsed['processes'] == ['NANOPLOT', 'FILTLONG', 'FLYE', 'SKIP_ASSEMBLY_MARKER', 'MEDAKA']
        states = {name: t['status'] for name, t in parsed['tasks'].items()}
        assert states == {'FILTLONG (s1)': 'COMPLETED', 'NANOPLOT (s1)': 'RUNNING', 'FLYE (s1)': 'RUNNING'}

    def test_non_zero_exit_is_failed_and_retry_runs_again(self):
        from services.nextflow_progress import parse_run_log

        lines = [
            "x - [02/4ea087] Submitted process > FLYE (s1)",
            "x - Task completed > TaskHandler[id: 4; name: FLYE (s1); status: COMPLETED; exit: 137; error: -; workDir: /w]",
        ]
        assert parse_run_log(lines)['tasks']['FLYE (s1)']['status'] == 'FAILED'

        lines.append("x - [5a/aaaaaa] Re-submitted process > FLYE (s1)")
        assert parse_run_log(lines)['tasks']['FLYE (s1)']['status'] == 'RUNNING'


class TestFindRunLog:
    def test_matches_only_this_runs_outdir(self, tmp_path):
        from services.nextflow_progress import find_run_log

        (tmp_path / '.nextflow.log').write_text(LOG)

        assert find_run_log(tmp_path, '/results/s1', None) == tmp_path / '.nextflow.log'
        assert find_run_log(tmp_path, '/results/s1/', None) == tmp_path / '.nextflow.log'
        # A different sample whose name starts the same way
        assert find_run_log(tmp_path, '/results/s', None) is None
        assert find_run_log(tmp_path, '/results/other', None) is None

    def test_log_older_than_run_start_is_ignored(self, tmp_path):
        """Test the previous run's log is not shown while the input is still downloading"""
        from services.nextflow_progress import find_run_log

        log = tmp_path / '.nextflow.log'
        log.write_text(LOG)
        old = time.time() - 3600
        os.utime(log, (old, old))

        assert find_run_log(tmp_path, '/results/s1', datetime.utcnow()) is None


class TestBuildLiveStatus:
    def _parsed(self):
        from services.nextflow_progress import parse_run_log
        return parse_run_log(LOG.splitlines())

    def test_running_counts_with_expected_processes(self):
        """Test pending only counts processes a comparable run executed"""
        from services.nextflow_progress import build_live_status

        status = build_live_status(self._parsed(), [], {'NANOPLOT', 'FILTLONG', 'FLYE', 'MEDAKA'}, 'running')

        assert status['summary'] == {
            'total': 4, 'completed': 1, 'cached': 0, 'running': 2, 'failed': 0, 'aborted': 0, 'pending': 1,
            'not_started': 0,
        }
        assert status['progress'] == 25
        pending = [p['name'] for p in status['processes'] if p['pending']]
        assert pending == ['MEDAKA']

    def test_without_reference_all_declared_processes_pending(self):
        from services.nextflow_progress import build_live_status

        status = build_live_status(self._parsed(), [], None, 'running')

        assert status['summary']['pending'] == 2  # SKIP_ASSEMBLY_MARKER, MEDAKA

    def test_queued_run_lists_expected_processes(self):
        from services.nextflow_progress import build_live_status

        status = build_live_status({}, [], {'FLYE', 'MEDAKA'}, 'queued')

        assert status['summary']['pending'] == 2
        assert status['progress'] == 0

    def test_trace_row_supplies_details(self):
        from services.nextflow_progress import build_live_status

        trace = [{'task_id': '1', 'name': 'FILTLONG (s1)', 'status': 'COMPLETED', 'exit': '0',
                  'duration': '5.4s', '%cpu': '98%', 'rss': '1 GB'}]
        status = build_live_status(self._parsed(), trace, None, 'running')

        filtlong = next(t for t in status['tasks'] if t['name'] == 'FILTLONG (s1)')
        assert filtlong['duration'] == '5.4s'

    def test_progress_never_100_while_running(self):
        from services.nextflow_progress import build_live_status

        parsed = {'processes': ['A'], 'tasks': {'A (s)': {'name': 'A (s)', 'status': 'COMPLETED', 'exit': '0'}}}

        assert build_live_status(parsed, [], {'A'}, 'running')['progress'] == 99
        assert build_live_status(parsed, [], {'A'}, 'completed')['progress'] == 100

    def test_cancelled_run_marks_stopped_tasks_aborted(self):
        from services.nextflow_progress import build_live_status

        parsed = {'processes': ['A', 'B', 'C'], 'tasks': {
            'A (s)': {'name': 'A (s)', 'status': 'COMPLETED', 'exit': '0'},
            'B (s)': {'name': 'B (s)', 'status': 'FAILED', 'exit': '143'},
        }}
        status = build_live_status(parsed, [], {'A', 'B', 'C'}, 'cancelled')

        assert status['summary']['aborted'] == 1
        assert status['summary']['failed'] == 0
        assert status['summary']['pending'] == 0
        assert status['summary']['not_started'] == 1
        assert status['progress'] == 33  # A done out of A, B, C
        assert not any(p['pending'] for p in status['processes'])


def _authed_request(conn):
    from auth import generate_token

    token = generate_token(user_id=7, username="johndoe", email="john@example.com")
    request = Mock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.ctx = Mock()
    acquire = Mock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=False)
    request.app.ctx.db_pool.acquire = Mock(return_value=acquire)
    return request


class TestCancelRunRoute:
    @pytest.mark.asyncio
    async def test_running_run_is_marked_cancelled(self):
        """Test a started job is left for the worker to stop"""
        from routes.pipeline_v2 import cancel_run_endpoint

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={'pipeline_id': 42, 'job_id': 'job-1'})

        with patch('routes.pipeline_v2.dequeue_job', return_value=False) as dequeue:
            response = await cancel_run_endpoint(_authed_request(conn), 42)

        body = json.loads(response.body)
        assert response.status == 200
        assert body['status'] == 'cancelled'
        assert 'stopping' in body['message']
        query, pipeline_id, user_id = conn.fetchrow.await_args.args
        assert "status IN ('queued', 'running')" in query and "owner_id = $2" in query
        assert (pipeline_id, user_id) == (42, 7)
        dequeue.assert_called_once_with('job-1')

    @pytest.mark.asyncio
    async def test_finished_run_cannot_be_cancelled(self):
        from routes.pipeline_v2 import cancel_run_endpoint

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value='completed')

        with patch('routes.pipeline_v2.dequeue_job') as dequeue:
            response = await cancel_run_endpoint(_authed_request(conn), 42)

        assert response.status == 400
        dequeue.assert_not_called()

    @pytest.mark.asyncio
    async def test_other_users_run_is_404(self):
        from routes.pipeline_v2 import cancel_run_endpoint

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        conn.fetchval = AsyncMock(return_value=None)

        response = await cancel_run_endpoint(_authed_request(conn), 42)

        assert response.status == 404


class TestRunNextflowCancellable:
    """Runs a real child process standing in for Nextflow"""

    SCRIPT = (
        "import signal, sys, time\n"
        "def stop(*_):\n"
        "    print('stopping tasks'); sys.stdout.flush(); sys.exit(143)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "print('started'); sys.stdout.flush()\n"
        "time.sleep(30)\n"
    )

    def _executor(self):
        from tasks.pipeline_tasks import PipelineExecutor
        return PipelineExecutor.__new__(PipelineExecutor)

    def test_cancel_sends_sigterm_and_keeps_output(self):
        """Test a cancelled run gets SIGTERM (so Nextflow can stop its containers)"""
        executor = self._executor()
        checks = iter([False, True])

        with patch('tasks.pipeline_tasks.CANCEL_POLL_SECONDS', 0.2), \
             patch.object(type(executor), 'is_cancelled', lambda self, pid: next(checks, True)):
            started = time.monotonic()
            result, cancelled = executor.run_nextflow_cancellable(
                1, [sys.executable, '-c', self.SCRIPT], cwd='.', env=dict(os.environ)
            )

        assert cancelled is True
        assert result.returncode == 143
        assert 'started' in result.stdout and 'stopping tasks' in result.stdout
        assert time.monotonic() - started < 10

    def test_uncancelled_run_returns_normally(self):
        executor = self._executor()

        with patch('tasks.pipeline_tasks.CANCEL_POLL_SECONDS', 0.2), \
             patch.object(type(executor), 'is_cancelled', lambda self, pid: False):
            result, cancelled = executor.run_nextflow_cancellable(
                1, [sys.executable, '-c', "print('done')"], cwd='.', env=dict(os.environ)
            )

        assert (cancelled, result.returncode, result.stdout.strip()) == (False, 0, 'done')

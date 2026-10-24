"""
Tests for deleting a sample (services/sample_deletion.py, DELETE /api/samples/<id>)
"""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, MagicMock, patch

import pytest


def _conn(sample, runs, shared=(), objects=()):
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = Mock(return_value=tx)
    conn.fetchrow = AsyncMock(return_value=sample)
    conn.fetch = AsyncMock(side_effect=[runs, list(shared), list(objects), [{'execution_id': 9}]])
    return conn


RUN = {'pipeline_id': 7, 'status': 'completed', 'sample_name': 'S1', 'results_path': '/results/S1',
       'nextflow_execution_id': 3}


class TestDeleteSampleRecords:
    @pytest.mark.asyncio
    async def test_unknown_or_foreign_sample(self):
        from services.sample_deletion import delete_sample_records, SampleNotFound

        conn = _conn(None, [])
        with pytest.raises(SampleNotFound):
            await delete_sample_records(conn, 7, 99)
        query, sample_id, user_id = conn.fetchrow.await_args.args
        assert 'owner_id = $2' in query and (sample_id, user_id) == (99, 7)

    @pytest.mark.asyncio
    async def test_active_run_blocks_deletion(self):
        from services.sample_deletion import delete_sample_records, SampleHasActiveRuns

        conn = _conn({'sample_id': 1, 'sample_code': 'S1'}, [dict(RUN, status='running')])
        with pytest.raises(SampleHasActiveRuns) as err:
            await delete_sample_records(conn, 7, 1)
        assert err.value.pipeline_ids == [7]
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deletes_rows_and_reports_files(self):
        from services.sample_deletion import delete_sample_records

        objects = [{'object_id': 5, 'bucket_name': 'genomic-silver', 'object_key': 'S1/7/x.txt', 'execution_id': 4}]
        conn = _conn({'sample_id': 1, 'sample_code': 'S1'}, [RUN], objects=objects)

        cleanup = await delete_sample_records(conn, 7, 1)

        statements = [c.args[0] for c in conn.execute.await_args_list]
        assert any('DELETE FROM data_lineage' in q for q in statements)
        assert any('DELETE FROM minio_objects' in q for q in statements)
        assert any('DELETE FROM samples' in q for q in statements)
        executions = next(c.args for c in conn.execute.await_args_list if 'DELETE FROM nextflow_executions' in c.args[0])
        assert executions[1] == [3, 4, 9]  # run link, uploaded files, job-name match
        named_query, patterns = conn.fetch.await_args_list[3].args
        assert patterns == ['^rq_job_[0-9a-f-]{36}_S1$']
        assert cleanup['prefixes'] == ['S1']
        assert cleanup['object_keys'] == [('genomic-silver', 'S1/7/x.txt')]
        assert cleanup['runs'] == 1

    @pytest.mark.asyncio
    async def test_prefix_used_by_another_sample_is_kept(self):
        """Test files are never removed by a prefix another sample owns"""
        from services.sample_deletion import delete_sample_records

        run = dict(RUN, sample_name='OTHER')
        conn = _conn({'sample_id': 1, 'sample_code': 'S1'}, [run], shared=[{'sample_code': 'OTHER'}])

        cleanup = await delete_sample_records(conn, 7, 1)

        assert cleanup['prefixes'] == ['S1']
        assert not any('OTHER' in str(d) for d in cleanup['local_dirs'])


class TestLocalDirs:
    def test_only_dirs_inside_results_and_work_dirs(self):
        from services.sample_deletion import _local_dirs
        from config import config

        runs = [dict(RUN, results_path='/etc'), dict(RUN, results_path=str(config.RESULTS_DIR / 'S1'))]
        dirs = _local_dirs(runs, ['S1'])

        assert Path('/etc') not in dirs
        assert set(dirs) == {(config.RESULTS_DIR / 'S1').resolve(), config.RESULTS_DIR / 'S1', config.WORK_DIR / 'S1'}


class TestRemoveSampleFiles:
    def test_removes_registered_and_prefixed_objects(self, tmp_path):
        from services.sample_deletion import remove_sample_files

        minio = Mock()
        minio.list_objects = Mock(side_effect=lambda bucket, prefix, recursive: (
            [SimpleNamespace(object_name='S1/assembly/a.fasta')] if bucket == 'genomic-gold' else []
        ))
        minio.remove_objects = Mock(return_value=iter([]))
        local = tmp_path / 'S1'
        local.mkdir()
        (local / 'f.txt').write_text('x')

        result = remove_sample_files(minio, {
            'sample_code': 'S1', 'prefixes': ['S1'],
            'object_keys': [('genomic-silver', 'S1/7/x.txt')], 'local_dirs': [local],
        })

        removed = {call.args[0]: [o._name for o in call.args[1]] for call in minio.remove_objects.call_args_list}
        assert removed == {'genomic-silver': ['S1/7/x.txt'], 'genomic-gold': ['S1/assembly/a.fasta']}
        assert result == {'objects_removed': 2, 'errors': []}
        assert not local.exists()


def _authed_request():
    from auth import generate_token

    token = generate_token(user_id=7, username="johndoe", email="john@example.com")
    request = Mock()
    request.headers = {"Authorization": f"Bearer {token}"}
    request.ctx = Mock()
    return request


class TestDeleteSampleRoute:
    @pytest.mark.asyncio
    async def test_active_run_is_409(self):
        from routes.samples import delete_sample
        from services.sample_deletion import SampleHasActiveRuns

        with patch('services.sample_deletion.delete_sample', new=AsyncMock(side_effect=SampleHasActiveRuns([7]))), \
             patch('minio_helper.get_minio_client'):
            response = await delete_sample(_authed_request(), 1)

        assert response.status == 409
        assert json.loads(response.body)['pipeline_ids'] == [7]

    @pytest.mark.asyncio
    async def test_deleted_for_token_user(self):
        from routes.samples import delete_sample

        result = {'sample_code': 'S1', 'runs_deleted': 1, 'objects_removed': 3, 'storage_errors': 0}
        with patch('services.sample_deletion.delete_sample', new=AsyncMock(return_value=result)) as delete, \
             patch('minio_helper.get_minio_client'):
            response = await delete_sample(_authed_request(), 1)

        assert response.status == 200
        assert json.loads(response.body) == {'success': True, **result}
        assert delete.await_args.args[2:] == (7, 1)

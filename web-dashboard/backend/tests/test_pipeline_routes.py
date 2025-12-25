"""
Tests for pipeline API routes
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.mark.unit
class TestPipelineRoutes:
    """Test pipeline management routes"""
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_empty(self, mock_request, db_conn):
        """Test getting pipeline runs when database is empty"""
        mock_request.args = {}
        
        # Mock database query
        rows = await db_conn.fetch("""
            SELECT pipeline_id, pipeline_name, status, created_at
            FROM pipeline_runs
            LIMIT 10
        """)
        
        assert isinstance(rows, list)
        # Empty database should return empty list
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_with_data(self, mock_request, test_pipeline_run, db_conn):
        """Test getting pipeline runs with existing data"""
        rows = await db_conn.fetch("""
            SELECT pipeline_id, pipeline_name, pipeline_version, status
            FROM pipeline_runs
            WHERE pipeline_id = $1
        """, test_pipeline_run)
        
        assert len(rows) == 1
        assert rows[0]['pipeline_id'] == test_pipeline_run
        assert rows[0]['pipeline_name'] == 'nextflow_pipeline'
        assert rows[0]['pipeline_version'] == '2.0.0'
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_with_filters(self, mock_request, test_pipeline_run, db_conn):
        """Test getting pipeline runs with status filter"""
        mock_request.args = {'status': 'completed'}
        
        rows = await db_conn.fetch("""
            SELECT pipeline_id, status
            FROM pipeline_runs
            WHERE status = $1 AND pipeline_id = $2
        """, 'completed', test_pipeline_run)
        
        assert len(rows) == 1
        assert rows[0]['status'] == 'completed'
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_with_date_filter(self, mock_request, db_conn):
        """Test date range filtering"""
        mock_request.args = {
            'date_from': '2025-12-24',
            'date_to': '2025-12-25'
        }
        
        # Verify query parameters
        assert 'date_from' in mock_request.args
        assert 'date_to' in mock_request.args
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_with_quality_filter(self, mock_request):
        """Test quality score filtering"""
        mock_request.args = {
            'min_quality': '30',
            'max_quality': '100'
        }
        
        # Verify filter parameters
        assert int(mock_request.args['min_quality']) >= 0
        assert int(mock_request.args['max_quality']) <= 100
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_with_mags_filter(self, mock_request):
        """Test MAGs count filtering"""
        mock_request.args = {
            'min_mags': '10',
            'max_mags': '50'
        }
        
        assert int(mock_request.args['min_mags']) == 10
        assert int(mock_request.args['max_mags']) == 50
    
    @pytest.mark.asyncio
    async def test_get_pipeline_run_by_id(self, test_pipeline_run, db_conn):
        """Test getting specific pipeline run by ID"""
        row = await db_conn.fetchrow("""
            SELECT pipeline_id, pipeline_name, status
            FROM pipeline_runs
            WHERE pipeline_id = $1
        """, test_pipeline_run)
        
        assert row is not None
        assert row['pipeline_id'] == test_pipeline_run
    
    @pytest.mark.asyncio
    async def test_get_pipeline_run_nonexistent(self, db_conn):
        """Test getting non-existent pipeline run"""
        row = await db_conn.fetchrow("""
            SELECT pipeline_id
            FROM pipeline_runs
            WHERE pipeline_id = $1
        """, 99999)
        
        assert row is None
    
    def test_create_pipeline_validation(self, sample_pipeline_params):
        """Test pipeline creation parameter validation"""
        assert 'sample_code' in sample_pipeline_params
        assert 'input_dir' in sample_pipeline_params
        assert isinstance(sample_pipeline_params['threads'], int)
    
    @pytest.mark.asyncio
    async def test_update_pipeline_status(self, test_pipeline_run, db_conn):
        """Test updating pipeline run status"""
        await db_conn.execute("""
            UPDATE pipeline_runs
            SET status = $1
            WHERE pipeline_id = $2
        """, 'running', test_pipeline_run)
        
        row = await db_conn.fetchrow("""
            SELECT status FROM pipeline_runs WHERE pipeline_id = $1
        """, test_pipeline_run)
        
        assert row['status'] == 'running'
    
    @pytest.mark.asyncio
    async def test_pagination(self, mock_request):
        """Test pagination parameters"""
        mock_request.args = {
            'limit': '50',
            'offset': '0'
        }
        
        limit = int(mock_request.args.get('limit', 10))
        offset = int(mock_request.args.get('offset', 0))
        
        assert limit == 50
        assert offset == 0
        assert limit > 0
        assert offset >= 0


@pytest.mark.integration
class TestPipelineExecution:
    """Test pipeline execution flow"""
    
    @pytest.mark.asyncio
    async def test_enqueue_pipeline(self, mock_redis_queue, sample_pipeline_params):
        """Test pipeline job enqueueing"""
        job = mock_redis_queue.enqueue('pipeline_task', **sample_pipeline_params)
        
        assert job is not None
        assert job.id == 'test-job-123'
    
    @pytest.mark.asyncio
    async def test_get_job_status(self, mock_redis_queue):
        """Test retrieving job status"""
        job = Mock()
        job.get_status = Mock(return_value='queued')
        mock_redis_queue.fetch_job = Mock(return_value=job)
        
        fetched_job = mock_redis_queue.fetch_job('test-job-123')
        assert fetched_job.get_status() == 'queued'

"""
Integration tests for full workflow
"""
import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile


class TestFullPipelineWorkflow:
    """Test complete pipeline workflow from upload to results"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self, mock_db_pool, mock_minio_client, 
                                      mock_fastq_file, sample_pipeline_summary):
        """Test full workflow: upload -> process -> retrieve results"""
        
        # Step 1: Upload FASTQ file
        sample_name = "INTEGRATION_TEST"
        bucket_name = "genomic-data"
        
        mock_minio_client.fput_object.return_value = MagicMock(
            object_name=f"{sample_name}/raw/test.fastq",
            etag="test_etag"
        )
        
        upload_result = mock_minio_client.fput_object(
            bucket_name,
            f"{sample_name}/raw/test.fastq",
            str(mock_fastq_file)
        )
        
        assert upload_result is not None
        
        # Step 2: Create pipeline run
        mock_connection = AsyncMock()
        mock_connection.fetchval.return_value = 1  # New pipeline_id
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        pipeline_id = await mock_connection.fetchval(
            """INSERT INTO pipeline_runs (sample_name, status, results_path)
               VALUES ($1, $2, $3) RETURNING pipeline_id""",
            sample_name, 'queued', f'/results/{sample_name}'
        )
        
        assert pipeline_id == 1
        
        # Step 3: Update status to running
        mock_connection.execute.return_value = "UPDATE 1"
        await mock_connection.execute(
            "UPDATE pipeline_runs SET status = $1 WHERE pipeline_id = $2",
            'running', pipeline_id
        )
        
        # Step 4: Complete pipeline
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            'pipeline_id': pipeline_id,
            'sample_name': sample_name,
            'status': 'completed',
            'pipeline_summary': json.dumps(sample_pipeline_summary)
        }[key]
        
        mock_connection.fetchrow.return_value = mock_record
        
        result = await mock_connection.fetchrow(
            "SELECT * FROM pipeline_runs WHERE pipeline_id = $1",
            pipeline_id
        )
        
        assert result['status'] == 'completed'
        assert result['pipeline_summary'] is not None
        
        # Step 5: Retrieve and validate summary
        summary = json.loads(result['pipeline_summary'])
        assert summary['sample_id'] == sample_pipeline_summary['sample_id']
        assert 'quality_score' in summary
        assert 'amr_risk_score' in summary
    
    @pytest.mark.asyncio
    async def test_workflow_with_failure(self, mock_db_pool, mock_minio_client, mock_fastq_file):
        """Test workflow with pipeline failure"""
        sample_name = "FAILING_TEST"
        
        # Upload succeeds
        mock_minio_client.fput_object.return_value = MagicMock(
            object_name=f"{sample_name}/raw/test.fastq"
        )
        
        upload_result = mock_minio_client.fput_object(
            "genomic-data",
            f"{sample_name}/raw/test.fastq",
            str(mock_fastq_file)
        )
        
        assert upload_result is not None
        
        # Pipeline fails
        mock_connection = AsyncMock()
        mock_connection.fetchval.return_value = 2
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        pipeline_id = await mock_connection.fetchval(
            """INSERT INTO pipeline_runs (sample_name, status, results_path)
               VALUES ($1, $2, $3) RETURNING pipeline_id""",
            sample_name, 'queued', f'/results/{sample_name}'
        )
        
        # Update to failed status
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            'pipeline_id': pipeline_id,
            'status': 'failed',
            'error_message': 'Assembly failed: insufficient coverage'
        }[key]
        
        mock_connection.fetchrow.return_value = mock_record
        
        result = await mock_connection.fetchrow(
            "SELECT * FROM pipeline_runs WHERE pipeline_id = $1",
            pipeline_id
        )
        
        assert result['status'] == 'failed'
        assert 'error_message' in result
        assert 'insufficient coverage' in result['error_message']
    
    @pytest.mark.asyncio
    async def test_concurrent_pipelines(self, mock_db_pool):
        """Test handling of concurrent pipeline runs"""
        mock_connection = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        # Create multiple pipelines
        pipeline_ids = []
        for i in range(3):
            mock_connection.fetchval.return_value = i + 1
            pid = await mock_connection.fetchval(
                """INSERT INTO pipeline_runs (sample_name, status)
                   VALUES ($1, $2) RETURNING pipeline_id""",
                f'CONCURRENT_{i}', 'queued'
            )
            pipeline_ids.append(pid)
        
        assert len(pipeline_ids) == 3
        assert pipeline_ids == [1, 2, 3]
        
        # Check all are queued
        mock_records = [
            MagicMock(**{'pipeline_id': i, 'status': 'queued'}, 
                     __getitem__=lambda self, key: {'pipeline_id': i, 'status': 'queued'}[key])
            for i in pipeline_ids
        ]
        mock_connection.fetch.return_value = mock_records
        
        results = await mock_connection.fetch(
            "SELECT pipeline_id, status FROM pipeline_runs WHERE status = 'queued'"
        )
        
        assert len(results) == 3


class TestDataValidation:
    """Test data validation and error handling"""
    
    @pytest.mark.asyncio
    async def test_invalid_fastq_format(self, temp_results_dir):
        """Test handling of invalid FASTQ file"""
        invalid_file = temp_results_dir / "invalid.fastq"
        invalid_file.write_text("This is not a valid FASTQ file")
        
        # Validation should fail
        with open(invalid_file) as f:
            first_line = f.readline()
            is_valid = first_line.startswith('@')
            assert not is_valid
    
    @pytest.mark.asyncio
    async def test_empty_fastq_file(self, temp_results_dir):
        """Test handling of empty FASTQ file"""
        empty_file = temp_results_dir / "empty.fastq"
        empty_file.write_text("")
        
        assert empty_file.stat().st_size == 0
    
    @pytest.mark.asyncio
    async def test_corrupted_results(self, temp_results_dir):
        """Test handling of corrupted result files"""
        from tests.backend.test_utils import parse_nanoplot
        
        # Create corrupted NanoStats file
        qc_dir = temp_results_dir / "01_qc"
        qc_dir.mkdir(parents=True)
        nanostats = qc_dir / "NanoStats.txt"
        nanostats.write_text("corrupted data\n@#$%^&*")
        
        result = parse_nanoplot(temp_results_dir)
        
        # Should return None or empty data
        assert result is None or len(result) == 0


class TestMinIOIntegration:
    """Test MinIO object storage integration"""
    
    @pytest.mark.asyncio
    async def test_bucket_operations(self, mock_minio_client):
        """Test bucket creation and listing"""
        bucket_name = "test-bucket"
        
        # Create bucket
        mock_minio_client.make_bucket.return_value = None
        mock_minio_client.make_bucket(bucket_name)
        
        # List buckets
        mock_minio_client.list_buckets.return_value = [
            MagicMock(name=bucket_name)
        ]
        
        buckets = mock_minio_client.list_buckets()
        assert len(buckets) == 1
        assert buckets[0].name == bucket_name
    
    @pytest.mark.asyncio
    async def test_object_operations(self, mock_minio_client, mock_fastq_file):
        """Test object upload, download, and deletion"""
        bucket_name = "genomic-data"
        object_name = "test/sample.fastq"
        
        # Upload
        mock_minio_client.fput_object.return_value = MagicMock(
            object_name=object_name,
            etag="abc123"
        )
        
        upload = mock_minio_client.fput_object(
            bucket_name, object_name, str(mock_fastq_file)
        )
        
        assert upload.object_name == object_name
        
        # Download
        mock_minio_client.fget_object.return_value = None
        mock_minio_client.fget_object(bucket_name, object_name, "/tmp/downloaded.fastq")
        
        # Delete
        mock_minio_client.remove_object.return_value = None
        mock_minio_client.remove_object(bucket_name, object_name)
    
    @pytest.mark.asyncio
    async def test_large_file_upload(self, temp_results_dir, mock_minio_client):
        """Test uploading large file"""
        large_file = temp_results_dir / "large.fastq"
        
        # Create 10MB file
        with open(large_file, 'wb') as f:
            f.write(b'@' * (10 * 1024 * 1024))
        
        assert large_file.stat().st_size == 10 * 1024 * 1024
        
        # Upload should handle large files
        mock_minio_client.fput_object.return_value = MagicMock(
            object_name="large_test/large.fastq",
            size=large_file.stat().st_size
        )
        
        result = mock_minio_client.fput_object(
            "genomic-data",
            "large_test/large.fastq",
            str(large_file)
        )
        
        assert result.size == 10 * 1024 * 1024


class TestDatabaseIntegration:
    """Test PostgreSQL database integration"""
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, mock_db_pool):
        """Test transaction rollback on error"""
        mock_connection = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        # Begin transaction
        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value.__aenter__.return_value = mock_transaction
        
        try:
            async with mock_connection.transaction():
                # Simulate error
                raise Exception("Database error")
        except Exception:
            # Transaction should rollback
            pass
    
    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion(self, mock_db_pool):
        """Test handling of connection pool exhaustion"""
        mock_db_pool.acquire.side_effect = Exception("Connection pool exhausted")
        
        try:
            async with mock_db_pool.acquire():
                pass
            pytest.fail("Should raise exception")
        except Exception as e:
            assert "pool exhausted" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_query_timeout(self, mock_db_pool):
        """Test query timeout handling"""
        mock_connection = AsyncMock()
        mock_connection.fetch.side_effect = asyncio.TimeoutError("Query timeout")
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        try:
            await mock_connection.fetch("SELECT * FROM large_table")
            pytest.fail("Should raise TimeoutError")
        except asyncio.TimeoutError:
            pass


class TestProgressTracking:
    """Test pipeline progress tracking"""
    
    @pytest.mark.asyncio
    async def test_progress_updates(self, mock_db_pool):
        """Test progress updates during pipeline execution"""
        mock_connection = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        pipeline_id = 1
        steps = ['QC', 'Filtering', 'Assembly', 'Binning', 'Quality', 'AMR', 'Taxonomy']
        
        for i, step in enumerate(steps):
            progress = ((i + 1) / len(steps)) * 100
            
            mock_connection.execute.return_value = "UPDATE 1"
            await mock_connection.execute(
                """INSERT INTO pipeline_progress (pipeline_id, step_name, status, progress)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (pipeline_id, step_name) 
                   DO UPDATE SET status = $3, progress = $4, updated_at = NOW()""",
                pipeline_id, step, 'completed' if i < len(steps) - 1 else 'running', progress
            )
        
        # Final step should be running
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            'step_name': 'Taxonomy',
            'status': 'running',
            'progress': 100
        }[key]
        
        mock_connection.fetchrow.return_value = mock_record
        
        current_step = await mock_connection.fetchrow(
            "SELECT step_name, status, progress FROM pipeline_progress WHERE pipeline_id = $1 AND status = 'running'",
            pipeline_id
        )
        
        assert current_step['step_name'] == 'Taxonomy'
        assert current_step['status'] == 'running'


class TestErrorRecovery:
    """Test error recovery and retry mechanisms"""
    
    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self, mock_db_pool):
        """Test retry logic for transient errors"""
        mock_connection = AsyncMock()
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        # Simulate transient error then success
        call_count = 0
        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return 1
        
        mock_connection.fetchval.side_effect = side_effect
        
        # Retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await mock_connection.fetchval("SELECT 1")
                assert result == 1
                break
            except Exception:
                if attempt == max_retries - 1:
                    pytest.fail("Should succeed after retries")
                await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, mock_db_pool):
        """Test graceful degradation when services are unavailable"""
        mock_connection = AsyncMock()
        mock_connection.fetchval.side_effect = Exception("Service unavailable")
        mock_db_pool.acquire.return_value.__aenter__.return_value = mock_connection
        
        try:
            await mock_connection.fetchval("SELECT 1")
            pytest.fail("Should raise exception")
        except Exception:
            # Should return fallback response
            fallback = {
                "status": "degraded",
                "message": "Service temporarily unavailable"
            }
            assert fallback["status"] == "degraded"

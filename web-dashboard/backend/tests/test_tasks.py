"""
Tests for Background Tasks (Pipeline, Compression, Retention)
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime


class TestPipelineLogger:
    """Tests for PipelineLogger class"""

    def test_logger_init(self):
        """Test PipelineLogger initialization"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(
            pipeline_id=1,
            sample_code="SAMPLE001",
            job_id="job-123"
        )
        
        assert logger.pipeline_id == 1
        assert logger.sample_code == "SAMPLE001"
        assert logger.job_id == "job-123"
        assert "pipeline=1" in logger._prefix
        assert "sample=SAMPLE001" in logger._prefix
        assert "job=job-123" in logger._prefix

    def test_logger_init_without_job_id(self):
        """Test PipelineLogger without job_id"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(
            pipeline_id=2,
            sample_code="SAMPLE002"
        )
        
        assert logger.job_id is None
        assert "job=" not in logger._prefix

    @patch('tasks.pipeline_tasks.logger')
    def test_logger_info(self, mock_logger):
        """Test PipelineLogger info logging"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(pipeline_id=1, sample_code="S001")
        logger.info("Test message", key="value")
        
        mock_logger.info.assert_called_once()
        call_args = str(mock_logger.info.call_args)
        assert "Test message" in call_args

    @patch('tasks.pipeline_tasks.logger')
    def test_logger_error(self, mock_logger):
        """Test PipelineLogger error logging"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(pipeline_id=1, sample_code="S001")
        logger.error("Error message", code=500)
        
        mock_logger.error.assert_called_once()

    @patch('tasks.pipeline_tasks.logger')
    def test_logger_warning(self, mock_logger):
        """Test PipelineLogger warning logging"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(pipeline_id=1, sample_code="S001")
        logger.warning("Warning message")
        
        mock_logger.warning.assert_called_once()

    @patch('tasks.pipeline_tasks.logger')
    def test_logger_debug(self, mock_logger):
        """Test PipelineLogger debug logging"""
        from tasks.pipeline_tasks import PipelineLogger
        
        logger = PipelineLogger(pipeline_id=1, sample_code="S001")
        logger.debug("Debug message", detail="info")
        
        mock_logger.debug.assert_called_once()


class TestPipelineExecutor:
    """Tests for PipelineExecutor class"""

    def test_executor_init(self):
        """Test PipelineExecutor initialization"""
        from tasks.pipeline_tasks import PipelineExecutor
        
        executor = PipelineExecutor()
        
        assert executor.nextflow_dir is not None
        assert executor.results_dir is not None

    @pytest.mark.asyncio
    @patch('tasks.pipeline_tasks.asyncpg.connect')
    async def test_update_pipeline_status(self, mock_connect):
        """Test updating pipeline status"""
        from tasks.pipeline_tasks import PipelineExecutor
        
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        
        executor = PipelineExecutor()
        await executor.update_pipeline_status(
            pipeline_id=1,
            status="running"
        )
        
        mock_conn.execute.assert_called_once()
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('tasks.pipeline_tasks.asyncpg.connect')
    async def test_update_pipeline_status_with_error(self, mock_connect):
        """Test updating pipeline status with error message"""
        from tasks.pipeline_tasks import PipelineExecutor
        
        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn
        
        executor = PipelineExecutor()
        await executor.update_pipeline_status(
            pipeline_id=1,
            status="failed",
            error_message="Pipeline execution failed",
            exit_code=1
        )
        
        mock_conn.execute.assert_called_once()


class TestCompressionTasks:
    """Tests for compression tasks"""

    def test_compress_file_async_import(self):
        """Test compress_file_async can be imported"""
        from tasks.compression_tasks import compress_file_async
        assert callable(compress_file_async)

    def test_compress_file_async_exists(self):
        """Test compression function exists"""
        from tasks import compression_tasks
        assert hasattr(compression_tasks, 'compress_file_async')


class TestRetentionTasks:
    """Tests for retention policy tasks"""

    def test_enforce_retention_policy_import(self):
        """Test enforce_retention_policy can be imported"""
        from tasks.retention_tasks import enforce_retention_policy
        assert callable(enforce_retention_policy)

    @pytest.mark.asyncio
    @patch('tasks.retention_tasks.DatabasePool')
    @patch('tasks.retention_tasks.get_minio_client')
    async def test_enforce_retention_policy_runs(self, mock_minio, mock_db_pool):
        """Test retention policy enforcement"""
        from tasks.retention_tasks import enforce_retention_policy
        
        # Setup mock pool
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_db_pool.get_pool.return_value = mock_pool
        
        # Mock no buckets with retention
        mock_conn.fetch.return_value = []
        
        result = await enforce_retention_policy()
        
        assert "start_time" in result
        assert "buckets_processed" in result
        assert result["buckets_processed"] == 0


class TestTaskImports:
    """Tests for tasks module imports"""

    def test_import_pipeline_tasks(self):
        """Test importing from pipeline_tasks"""
        from tasks.pipeline_tasks import PipelineExecutor, PipelineLogger
        
        assert PipelineExecutor is not None
        assert PipelineLogger is not None

    def test_import_compression_tasks(self):
        """Test importing from compression_tasks"""
        from tasks.compression_tasks import compress_file_async
        
        assert compress_file_async is not None

    def test_import_retention_tasks(self):
        """Test importing from retention_tasks"""
        from tasks.retention_tasks import enforce_retention_policy
        
        assert enforce_retention_policy is not None


class TestTasksInit:
    """Tests for tasks __init__.py"""

    def test_tasks_package_imports(self):
        """Test tasks package can be imported"""
        import tasks
        assert tasks is not None

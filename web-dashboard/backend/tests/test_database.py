"""
Tests for database operations
"""
import pytest
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.mark.requires_db
@pytest.mark.unit
class TestDatabaseSamples:
    """Test database operations for samples"""
    
    @pytest.mark.asyncio
    async def test_create_sample(self, db_conn):
        """Test creating a new sample"""
        sample_id = await db_conn.fetchval("""
            INSERT INTO samples (
                sample_code, sample_type, sequencing_platform,
                collection_date, created_at
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING sample_id
        """, 'TEST_DB_001', 'nanopore', 'Oxford Nanopore',
            '2025-12-24', datetime.now())
        
        assert sample_id is not None
        assert isinstance(sample_id, int)
        
        # Cleanup
        await db_conn.execute("DELETE FROM samples WHERE sample_id = $1", sample_id)
    
    @pytest.mark.asyncio
    async def test_get_sample_by_code(self, test_sample, db_conn):
        """Test retrieving sample by code"""
        row = await db_conn.fetchrow("""
            SELECT sample_id, sample_code, sample_type
            FROM samples
            WHERE sample_code = $1
        """, 'TEST_SAMPLE_001')
        
        assert row is not None
        assert row['sample_code'] == 'TEST_SAMPLE_001'
        assert row['sample_type'] == 'nanopore'
    
    @pytest.mark.asyncio
    async def test_update_sample(self, test_sample, db_conn):
        """Test updating sample data"""
        await db_conn.execute("""
            UPDATE samples
            SET sequencing_platform = $1
            WHERE sample_id = $2
        """, 'Illumina NovaSeq', test_sample)
        
        row = await db_conn.fetchrow("""
            SELECT sequencing_platform
            FROM samples
            WHERE sample_id = $1
        """, test_sample)
        
        assert row['sequencing_platform'] == 'Illumina NovaSeq'
    
    @pytest.mark.asyncio
    async def test_delete_sample(self, db_conn):
        """Test deleting sample"""
        # Create temporary sample
        sample_id = await db_conn.fetchval("""
            INSERT INTO samples (
                sample_code, sample_type, sequencing_platform,
                collection_date, created_at
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING sample_id
        """, 'TEMP_SAMPLE', 'nanopore', 'Oxford Nanopore',
            '2025-12-24', datetime.now())
        
        # Delete it
        await db_conn.execute("DELETE FROM samples WHERE sample_id = $1", sample_id)
        
        # Verify deletion
        row = await db_conn.fetchrow("SELECT sample_id FROM samples WHERE sample_id = $1", sample_id)
        assert row is None
    
    @pytest.mark.asyncio
    async def test_unique_sample_code(self, test_sample, db_conn):
        """Test sample_code uniqueness constraint"""
        # Try to insert duplicate sample_code
        try:
            await db_conn.fetchval("""
                INSERT INTO samples (
                    sample_code, sample_type, sequencing_platform,
                    collection_date, created_at
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING sample_id
            """, 'TEST_SAMPLE_001', 'nanopore', 'Oxford Nanopore',
                '2025-12-24', datetime.now())
            assert False, "Should have raised unique constraint violation"
        except Exception as e:
            # Expected to fail with unique constraint violation
            assert 'unique' in str(e).lower() or 'duplicate' in str(e).lower()


@pytest.mark.requires_db
@pytest.mark.unit
class TestDatabasePipelineRuns:
    """Test database operations for pipeline runs"""
    
    @pytest.mark.asyncio
    async def test_create_pipeline_run(self, test_sample, db_conn):
        """Test creating pipeline run"""
        pipeline_id = await db_conn.fetchval("""
            INSERT INTO pipeline_runs (
                sample_id, pipeline_name, pipeline_version,
                status, results_path, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING pipeline_id
        """, test_sample, 'test_pipeline', '1.0.0',
            'queued', '/results/test', datetime.now())
        
        assert pipeline_id is not None
        
        # Cleanup
        await db_conn.execute("DELETE FROM pipeline_runs WHERE pipeline_id = $1", pipeline_id)
    
    @pytest.mark.asyncio
    async def test_get_pipeline_runs_by_sample(self, test_pipeline_run, test_sample, db_conn):
        """Test getting pipeline runs for a sample"""
        rows = await db_conn.fetch("""
            SELECT pipeline_id, pipeline_name, status
            FROM pipeline_runs
            WHERE sample_id = $1
        """, test_sample)
        
        assert len(rows) > 0
        assert rows[0]['pipeline_id'] == test_pipeline_run
    
    @pytest.mark.asyncio
    async def test_update_pipeline_status(self, test_pipeline_run, db_conn):
        """Test updating pipeline run status"""
        await db_conn.execute("""
            UPDATE pipeline_runs
            SET status = $1, started_at = $2
            WHERE pipeline_id = $3
        """, 'running', datetime.now(), test_pipeline_run)
        
        row = await db_conn.fetchrow("""
            SELECT status, started_at
            FROM pipeline_runs
            WHERE pipeline_id = $1
        """, test_pipeline_run)
        
        assert row['status'] == 'running'
        assert row['started_at'] is not None
    
    @pytest.mark.asyncio
    async def test_pipeline_run_timestamps(self, test_pipeline_run, db_conn):
        """Test pipeline run timestamp updates"""
        await db_conn.execute("""
            UPDATE pipeline_runs
            SET started_at = $1, completed_at = $2
            WHERE pipeline_id = $3
        """, datetime.now(), datetime.now(), test_pipeline_run)
        
        row = await db_conn.fetchrow("""
            SELECT started_at, completed_at
            FROM pipeline_runs
            WHERE pipeline_id = $1
        """, test_pipeline_run)
        
        assert row['started_at'] is not None
        assert row['completed_at'] is not None
        assert row['completed_at'] >= row['started_at']
    
    @pytest.mark.asyncio
    async def test_query_pipeline_runs_by_status(self, db_conn):
        """Test querying pipeline runs by status"""
        rows = await db_conn.fetch("""
            SELECT pipeline_id, status
            FROM pipeline_runs
            WHERE status = $1
        """, 'completed')
        
        for row in rows:
            assert row['status'] == 'completed'
    
    @pytest.mark.asyncio
    async def test_query_pipeline_runs_by_date_range(self, db_conn):
        """Test querying pipeline runs by date range"""
        rows = await db_conn.fetch("""
            SELECT pipeline_id, created_at
            FROM pipeline_runs
            WHERE created_at >= $1 AND created_at <= $2
        """, '2025-12-01', '2025-12-31')
        
        for row in rows:
            assert row['created_at'] is not None


@pytest.mark.requires_db
@pytest.mark.unit
class TestDatabaseJoins:
    """Test database join queries"""
    
    @pytest.mark.asyncio
    async def test_join_samples_and_pipeline_runs(self, test_pipeline_run, test_sample, db_conn):
        """Test joining samples with pipeline runs"""
        row = await db_conn.fetchrow("""
            SELECT 
                s.sample_code,
                pr.pipeline_name,
                pr.status
            FROM samples s
            INNER JOIN pipeline_runs pr ON s.sample_id = pr.sample_id
            WHERE pr.pipeline_id = $1
        """, test_pipeline_run)
        
        assert row is not None
        assert row['sample_code'] == 'TEST_SAMPLE_001'
        assert row['pipeline_name'] == 'nextflow_pipeline'
    
    @pytest.mark.asyncio
    async def test_count_pipeline_runs_per_sample(self, test_sample, db_conn):
        """Test counting pipeline runs per sample"""
        row = await db_conn.fetchrow("""
            SELECT 
                s.sample_code,
                COUNT(pr.pipeline_id) as run_count
            FROM samples s
            LEFT JOIN pipeline_runs pr ON s.sample_id = pr.sample_id
            WHERE s.sample_id = $1
            GROUP BY s.sample_code
        """, test_sample)
        
        assert row is not None
        assert row['run_count'] >= 0

"""
Pipeline run repository for database operations.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncpg
import json as json_lib

from .base_repository import BaseRepository
from models.pipeline_run import PipelineRun, PipelineRunCreate, PipelineRunUpdate


class PipelineRepository(BaseRepository[PipelineRun]):
    """Repository for pipeline run-related database operations."""
    
    @property
    def table_name(self) -> str:
        return "pipeline_runs"
    
    @property
    def primary_key(self) -> str:
        return "pipeline_id"
    
    def _parse_row(self, row) -> Dict[str, Any]:
        """Parse database row and convert JSON strings to dicts"""
        result = dict(row)
        # Parse parameters JSON string to dict
        if 'parameters' in result and isinstance(result['parameters'], str):
            try:
                result['parameters'] = json_lib.loads(result['parameters'])
            except (json_lib.JSONDecodeError, TypeError):
                result['parameters'] = {}
        return result
    
    async def find_by_id(self, id_value: int) -> Optional[Dict[str, Any]]:
        """Override to use _parse_row for JSON field parsing"""
        query = f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, id_value)
            return self._parse_row(row) if row else None
    
    async def create(self, run_data: PipelineRunCreate) -> int:
        """
        Create a new pipeline run record.
        
        Args:
            run_data: Pipeline run creation data
            
        Returns:
            ID of the created pipeline run
        """
        import json as json_module
        
        query = """
            INSERT INTO pipeline_runs (
                sample_id, pipeline_name, pipeline_version,
                software_name, software_version, parameters,
                reference_database, reference_db_version,
                cpu_cores, memory_gb, runtime_minutes,
                results_path, log_file_path, status,
                exit_code, error_message, sample_name, job_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
            )
            RETURNING pipeline_id
        """
        
        # Serialize parameters to JSON string
        parameters_json = json_module.dumps(run_data.parameters) if run_data.parameters else None
        
        async with self.pool.acquire() as conn:
            pipeline_id = await conn.fetchval(
                query,
                run_data.sample_id,
                run_data.pipeline_name,
                run_data.pipeline_version,
                run_data.software_name,
                run_data.software_version,
                parameters_json,
                run_data.reference_database,
                run_data.reference_db_version,
                run_data.cpu_cores,
                run_data.memory_gb,
                run_data.runtime_minutes,
                run_data.results_path,
                run_data.log_file_path,
                run_data.status,
                run_data.exit_code,
                run_data.error_message,
                run_data.sample_name,
                run_data.job_id
            )
            return pipeline_id
    
    async def update(self, pipeline_id: int, update_data: PipelineRunUpdate) -> bool:
        """
        Update an existing pipeline run.
        
        Args:
            pipeline_id: ID of pipeline run to update
            update_data: Fields to update
            
        Returns:
            True if pipeline run was updated, False if not found
        """
        import json as json_module
        
        # Build dynamic UPDATE query
        update_fields = []
        values = []
        param_idx = 1
        
        for field, value in update_data.model_dump(exclude_unset=True).items():
            # Serialize parameters to JSON string
            if field == 'parameters' and value is not None:
                value = json_module.dumps(value)
            
            update_fields.append(f"{field} = ${param_idx}")
            values.append(value)
            param_idx += 1
        
        if not update_fields:
            return False
        
        values.append(pipeline_id)
        query = f"""
            UPDATE pipeline_runs
            SET {', '.join(update_fields)}
            WHERE pipeline_id = ${param_idx}
            RETURNING pipeline_id
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, *values)
            return result is not None
    
    async def find_by_sample(
        self, 
        sample_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find all pipeline runs for a specific sample.
        
        Args:
            sample_id: ID of the sample
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of pipeline run dictionaries
        """
        query = """
            SELECT * FROM pipeline_runs
            WHERE sample_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, sample_id, limit, offset)
            return [self._parse_row(row) for row in rows]
    
    async def find_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Find pipeline runs by status.
        
        Args:
            status: Pipeline run status
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of pipeline run dictionaries
        """
        query = """
            SELECT * FROM pipeline_runs
            WHERE status = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, status, limit, offset)
            return [self._parse_row(row) for row in rows]
    
    async def find_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a pipeline run by background job ID.
        
        Args:
            job_id: Background job identifier
            
        Returns:
            Dictionary with pipeline run data or None
        """
        query = "SELECT * FROM pipeline_runs WHERE job_id = $1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, job_id)
            return self._parse_row(row) if row else None
    
    async def update_status(
        self,
        pipeline_id: int,
        status: str,
        error_message: Optional[str] = None,
        exit_code: Optional[int] = None
    ) -> bool:
        """
        Update the status of a pipeline run.
        
        Args:
            pipeline_id: ID of pipeline run
            status: New status
            error_message: Optional error message
            exit_code: Optional exit code
            
        Returns:
            True if updated successfully
        """
        now = datetime.now()
        
        # Set appropriate timestamp based on status
        if status == "running":
            query = """
                UPDATE pipeline_runs
                SET status = $1, started_at = $2
                WHERE pipeline_id = $3
                RETURNING pipeline_id
            """
            params = (status, now, pipeline_id)
        elif status in ("completed", "failed", "cancelled"):
            query = """
                UPDATE pipeline_runs
                SET status = $1, completed_at = $2, error_message = $3, exit_code = $4
                WHERE pipeline_id = $5
                RETURNING pipeline_id
            """
            params = (status, now, error_message, exit_code, pipeline_id)
        else:
            query = """
                UPDATE pipeline_runs
                SET status = $1
                WHERE pipeline_id = $2
                RETURNING pipeline_id
            """
            params = (status, pipeline_id)
        
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, *params)
            return result is not None
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get pipeline run statistics.
        
        Returns:
            Dictionary with counts by status
        """
        query = """
            SELECT 
                status,
                COUNT(*) as count,
                AVG(runtime_minutes) as avg_runtime
            FROM pipeline_runs
            GROUP BY status
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return {row['status']: {
                'count': row['count'],
                'avg_runtime': float(row['avg_runtime']) if row['avg_runtime'] else None
            } for row in rows}

    async def find_active_for_sample(self, sample_id: int) -> Optional[Dict[str, Any]]:
        """
        Find any active (queued/running) pipeline for a sample.
        Used for idempotency check before submission.
        
        Args:
            sample_id: Sample ID to check
            
        Returns:
            Active pipeline run or None
        """
        query = """
            SELECT * FROM pipeline_runs
            WHERE sample_id = $1 AND status IN ('queued', 'running', 'pending')
            ORDER BY created_at DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, sample_id)
            return self._parse_row(row) if row else None

    async def find_stuck_pipelines(
        self,
        queued_timeout_minutes: int = 60,
        running_timeout_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Find pipelines that appear stuck (queued too long or running too long).
        
        Args:
            queued_timeout_minutes: Minutes after which queued is considered stuck
            running_timeout_hours: Hours after which running is considered stuck
            
        Returns:
            List of stuck pipeline runs
        """
        query = """
            SELECT * FROM pipeline_runs
            WHERE
                (status = 'queued' AND created_at < NOW() - make_interval(mins => $1))
                OR
                (status = 'running' AND started_at < NOW() - make_interval(hours => $2))
            ORDER BY created_at ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, queued_timeout_minutes, running_timeout_hours)
            return [self._parse_row(row) for row in rows]

    async def mark_stuck_as_failed(
        self,
        queued_timeout_minutes: int = 60,
        running_timeout_hours: int = 24
    ) -> int:
        """
        Mark stuck pipelines as failed with appropriate error message.
        
        Returns:
            Number of pipelines marked as failed
        """
        query = """
            UPDATE pipeline_runs
            SET
                status = 'failed',
                completed_at = NOW(),
                error_message = CASE
                    WHEN status = 'queued' THEN 'Stuck in queue for over ' || $1 || ' minutes'
                    WHEN status = 'running' THEN 'Execution exceeded ' || $2 || ' hour timeout'
                END
            WHERE
                (status = 'queued' AND created_at < NOW() - make_interval(mins => $1))
                OR
                (status = 'running' AND started_at < NOW() - make_interval(hours => $2))
            RETURNING pipeline_id
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetch(query, queued_timeout_minutes, running_timeout_hours)
            return len(result)

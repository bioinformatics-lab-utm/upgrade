"""
Pipeline service implementing business logic for pipeline execution.
"""
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, date
import logging
import json

from models.pipeline_run import PipelineRun, PipelineRunCreate, PipelineRunUpdate
from repositories.pipeline_repository import PipelineRepository
from repositories.sample_repository import SampleRepository

if TYPE_CHECKING:
    from services.sample_service import SampleService
    from services.storage_service import StorageService

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Service for pipeline run-related business logic.
    
    Handles pipeline execution, status updates, and result tracking.
    """
    
    def __init__(
        self,
        pipeline_repo: PipelineRepository,
        sample_repo: SampleRepository,
        sample_service: Optional['SampleService'] = None,
        storage_service: Optional['StorageService'] = None
    ):
        """
        Initialize service with repositories.
        
        Args:
            pipeline_repo: Pipeline repository instance
            sample_repo: Sample repository instance
            sample_service: Sample service for business logic (optional, for cross-service calls)
            storage_service: Storage service for MinIO operations (optional, for upload preparation)
        """
        self.pipeline_repo = pipeline_repo
        self.sample_repo = sample_repo
        self.sample_service = sample_service
        self.storage_service = storage_service
    
    async def create_pipeline_run(
        self,
        run_data: PipelineRunCreate,
        allow_duplicate: bool = False
    ) -> int:
        """
        Create a new pipeline run with idempotency check.
        
        Args:
            run_data: Pipeline run creation data
            allow_duplicate: If False, raises error if active pipeline exists for sample
            
        Returns:
            ID of created pipeline run
            
        Raises:
            ValueError: If validation fails or duplicate active run exists
        """
        # Validate sample exists
        sample = await self.sample_repo.find_by_id(run_data.sample_id)
        if not sample:
            raise ValueError(f"Sample with ID {run_data.sample_id} not found")
        
        # IDEMPOTENCY CHECK: Atomic check-and-create using advisory lock
        # Prevents race condition where two concurrent requests both pass the check
        if not allow_duplicate:
            async with self.pipeline_repo.pool.acquire() as conn:
                async with conn.transaction():
                    # Advisory lock on sample_id prevents concurrent pipeline creation
                    await conn.execute("SELECT pg_advisory_xact_lock($1)", run_data.sample_id)

                    active_run = await conn.fetchrow("""
                        SELECT pipeline_id, status FROM pipeline_runs
                        WHERE sample_id = $1 AND status IN ('queued', 'running', 'pending')
                        ORDER BY created_at DESC LIMIT 1
                    """, run_data.sample_id)

                    if active_run:
                        existing_id = active_run['pipeline_id']
                        existing_status = active_run['status']
                        logger.warning(
                            f"[IDEMPOTENCY] Blocked duplicate pipeline for sample {run_data.sample_id}. "
                            f"Existing pipeline_id={existing_id} status={existing_status}"
                        )
                        raise ValueError(
                            f"Active pipeline already exists for this sample (pipeline_id={existing_id}, "
                            f"status={existing_status}). Wait for completion or cancel existing run."
                        )

        # Validate pipeline name
        valid_pipelines = [
            'nextflow_pipeline',
            'assembly_pipeline',
            'amr_pipeline',
            'pathogen_detection'
        ]
        if run_data.pipeline_name not in valid_pipelines:
            logger.warning(f"Unknown pipeline_name: {run_data.pipeline_name}")

        # Create pipeline run
        pipeline_id = await self.pipeline_repo.create(run_data)
        logger.info(
            f"[PIPELINE] Created pipeline_id={pipeline_id} sample_id={run_data.sample_id} "
            f"pipeline={run_data.pipeline_name}"
        )
        
        return pipeline_id
    
    async def get_pipeline_run(self, pipeline_id: int) -> Optional[PipelineRun]:
        """
        Get pipeline run by ID.
        
        Args:
            pipeline_id: Pipeline run ID
            
        Returns:
            PipelineRun model or None if not found
        """
        data = await self.pipeline_repo.find_by_id(pipeline_id)
        return PipelineRun(**data) if data else None
    
    async def get_pipeline_run_by_job_id(
        self,
        job_id: str
    ) -> Optional[PipelineRun]:
        """
        Get pipeline run by background job ID.
        
        Args:
            job_id: Background job identifier
            
        Returns:
            PipelineRun model or None if not found
        """
        data = await self.pipeline_repo.find_by_job_id(job_id)
        return PipelineRun(**data) if data else None
    
    async def update_pipeline_run(
        self,
        pipeline_id: int,
        update_data: PipelineRunUpdate
    ) -> bool:
        """
        Update an existing pipeline run.
        
        Args:
            pipeline_id: ID of pipeline run to update
            update_data: Fields to update
            
        Returns:
            True if updated, False if not found
        """
        # Check pipeline run exists
        existing = await self.pipeline_repo.find_by_id(pipeline_id)
        if not existing:
            return False
        
        return await self.pipeline_repo.update(pipeline_id, update_data)
    
    async def update_status(
        self,
        pipeline_id: int,
        status: str,
        error_message: Optional[str] = None,
        exit_code: Optional[int] = None
    ) -> bool:
        """
        Update pipeline run status with automatic timestamp handling.
        
        Args:
            pipeline_id: Pipeline run ID
            status: New status (queued, running, completed, failed, cancelled)
            error_message: Optional error message for failed runs
            exit_code: Optional exit code
            
        Returns:
            True if updated successfully
            
        Raises:
            ValueError: If invalid status
        """
        valid_statuses = ['queued', 'running', 'completed', 'failed', 'cancelled']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")
        
        success = await self.pipeline_repo.update_status(
            pipeline_id, status, error_message, exit_code
        )
        
        if success:
            logger.info(f"Pipeline {pipeline_id} status updated to {status}")
        
        return success
    
    async def list_pipeline_runs(
        self,
        sample_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PipelineRun]:
        """
        List pipeline runs with optional filters.
        
        Args:
            sample_id: Filter by sample ID
            status: Filter by status
            limit: Maximum number of records
            offset: Number of records to skip
            
        Returns:
            List of PipelineRun models
        """
        if sample_id:
            rows = await self.pipeline_repo.find_by_sample(sample_id, limit, offset)
        elif status:
            rows = await self.pipeline_repo.find_by_status(status, limit, offset)
        else:
            rows = await self.pipeline_repo.find_all(limit, offset)
        
        return [PipelineRun(**row) for row in rows]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get pipeline run statistics.
        
        Returns:
            Dictionary with statistics by status
        """
        return await self.pipeline_repo.get_statistics()
    
    async def count_by_status(self, status: str) -> int:
        """
        Count pipeline runs by status.
        
        Args:
            status: Pipeline run status
            
        Returns:
            Number of matching pipeline runs
        """
        return await self.pipeline_repo.count("status = $1", (status,))
    
    async def mark_as_running(self, pipeline_id: int) -> bool:
        """
        Mark a pipeline run as running (sets started_at timestamp).
        
        Args:
            pipeline_id: Pipeline run ID
            
        Returns:
            True if updated successfully
        """
        return await self.update_status(pipeline_id, 'running')
    
    async def mark_as_completed(
        self,
        pipeline_id: int,
        exit_code: int = 0
    ) -> bool:
        """
        Mark a pipeline run as completed (sets completed_at timestamp).
        
        Args:
            pipeline_id: Pipeline run ID
            exit_code: Exit code (default 0 for success)
            
        Returns:
            True if updated successfully
        """
        return await self.update_status(pipeline_id, 'completed', exit_code=exit_code)
    
    async def mark_as_failed(
        self,
        pipeline_id: int,
        error_message: str,
        exit_code: Optional[int] = None
    ) -> bool:
        """
        Mark a pipeline run as failed.
        
        Args:
            pipeline_id: Pipeline run ID
            error_message: Error description
            exit_code: Exit code
            
        Returns:
            True if updated successfully
        """
        return await self.update_status(
            pipeline_id, 'failed', error_message, exit_code
        )
    
    async def cancel_pipeline_run(self, pipeline_id: int) -> bool:
        """
        Cancel a pipeline run.
        
        Args:
            pipeline_id: Pipeline run ID
            
        Returns:
            True if cancelled successfully
        """
        return await self.update_status(pipeline_id, 'cancelled')
    
    async def prepare_upload(
        self,
        sample_code: str,
        sample_type: str,
        collection_date: date,
        files_info: List[Dict[str, Any]],
        pipeline_name: str = 'nextflow_pipeline',
        parameters: Optional[Dict[str, Any]] = None,
        notes: str = ''
    ) -> Dict[str, Any]:
        """
        Prepare sample upload: create sample, create pipeline run, generate presigned URLs.
        
        Args:
            sample_code: Sample identifier
            sample_type: Type of sample (nanopore, illumina, pacbio)
            collection_date: Sample collection date
            files_info: List of file info dicts with 'name' and 'size'
            pipeline_name: Pipeline name
            parameters: Pipeline parameters
            notes: Sample notes
            
        Returns:
            Dict with upload_urls, sample_id, pipeline_id
        """
        from pathlib import Path
        import os
        import re
        
        # Validate sample_code format
        if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', sample_code):
            raise ValueError('Invalid sample_code format. Use only alphanumeric, underscore, and hyphen (max 100 chars)')
        
        # Validate sample_type
        valid_sample_types = ['nanopore', 'illumina', 'pacbio']
        if sample_type not in valid_sample_types:
            raise ValueError(f'Invalid sample_type. Must be one of: {valid_sample_types}')
        
        # Create sample
        from models.sample import SampleCreate
        sample_create = SampleCreate(
            sample_code=sample_code,
            sample_type=sample_type,
            collection_date=collection_date,
            notes=notes
        )
        sample_id = await self.sample_service.create_sample(sample_create)
        
        # Create results directory
        results_path = f"/results/{sample_code}"
        log_path = f"{results_path}/nextflow.log"
        Path(results_path).mkdir(parents=True, exist_ok=True, mode=0o777)
        
        try:
            os.chmod(results_path, 0o777)
        except PermissionError:
            logger.warning(f"Cannot chmod {results_path}, assuming already writable")
        
        # Create pipeline run
        from models.pipeline_run import PipelineRunCreate
        pipeline_create = PipelineRunCreate(
            sample_id=sample_id,
            sample_name=sample_code,
            pipeline_name=pipeline_name,
            parameters=parameters or {},
            results_path=results_path,
            log_path=log_path,
            status='pending'
        )
        pipeline_id = await self.create_pipeline_run(pipeline_create)
        
        # Generate presigned URLs for each file
        storage_service = self.storage_service
        bronze_bucket = 'genomic-bronze'
        upload_urls = []
        
        for file_info in files_info:
            filename = file_info['name']
            
            # Sanitize filename
            filename = os.path.basename(filename)
            filename = filename.replace('\x00', '')
            
            object_path = f"{sample_code}/raw/{filename}"
            
            presigned_url = storage_service.generate_presigned_put_url(
                bronze_bucket,
                object_path,
                expires_seconds=3600
            )
            
            upload_urls.append({
                'filename': filename,
                'presigned_url': presigned_url,
                'object_path': object_path,
                'size': file_info.get('size', 0),
                'needs_compression': not filename.endswith('.gz')
            })
        
        return {
            'sample_id': sample_id,
            'pipeline_id': pipeline_id,
            'sample_code': sample_code,
            'upload_urls': upload_urls,
            'expires_in': 3600
        }
    
    async def confirm_upload(
        self,
        pipeline_id: int,
        sample_id: int,
        sample_code: str,
        uploaded_files: List[Dict[str, Any]],
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Confirm uploaded files and start pipeline processing.
        
        Verifies files in MinIO, compresses if needed, registers in DB,
        and enqueues pipeline execution.
        
        Args:
            pipeline_id: Pipeline run ID
            sample_id: Sample ID
            sample_code: Sample code
            uploaded_files: List of uploaded file info dicts
            parameters: Pipeline parameters
            
        Returns:
            Dict with job_id, status, timing info
        """
        import time
        import re
        
        start_time = time.time()
        
        # Validate inputs
        if not all([pipeline_id, sample_id, sample_code]):
            raise ValueError('pipeline_id, sample_id, and sample_code are required')
        
        if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', sample_code):
            raise ValueError('Invalid sample_code format')
        
        if not uploaded_files or not isinstance(uploaded_files, list):
            raise ValueError('uploaded_files array is required')
        
        if len(uploaded_files) > 50:
            raise ValueError('Maximum 50 files per upload')
        
        total_size_mb = sum(f.get('size', 0) for f in uploaded_files) / 1024 / 1024
        logger.info(
            f"[CONFIRM] Starting confirmation: pipeline={pipeline_id}, "
            f"sample={sample_code}, files={len(uploaded_files)} ({total_size_mb:.1f} MB)"
        )
        
        # Verify and process files using StorageService
        bronze_bucket = 'genomic-bronze'
        bronze_objects = []
        
        for idx, file_info in enumerate(uploaded_files):
            object_path = file_info['object_path']
            filename = file_info['filename']
            
            # Verify file exists
            try:
                metadata = self.storage_service.get_object_metadata(bronze_bucket, object_path)
                logger.info(
                    f"[CONFIRM] [{idx+1}/{len(uploaded_files)}] Verified {filename}: "
                    f"{metadata['size'] / 1024 / 1024:.1f} MB"
                )
                
                bronze_objects.append({
                    'filename': filename,
                    'object_path': object_path,
                    'size': metadata['size'],
                    'etag': metadata['etag']
                })
            except Exception as e:
                logger.error(f"[CONFIRM] File verification failed for {object_path}: {e}")
                raise ValueError(f'File not found in MinIO: {object_path}')
        
        # Register files in minio_objects table (required for download_from_bronze)
        # Wrapped in transaction for atomicity — all files or none
        async with self.pipeline_repo.pool.acquire() as conn:
            async with conn.transaction():
                # Resolve bucket_id upfront — fail fast if bucket doesn't exist
                bucket_id = await conn.fetchval(
                    "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1",
                    bronze_bucket
                )
                if bucket_id is None:
                    raise ValueError(f"Bucket '{bronze_bucket}' not found in minio_buckets table")

                for obj in bronze_objects:
                    await conn.execute("""
                        INSERT INTO minio_objects (
                            bucket_id, object_key, object_name, object_size_bytes,
                            content_type, etag, sample_id, pipeline_id, layer_stage
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'raw')
                    """,
                        bucket_id,
                        obj['object_path'],
                        obj['filename'],
                        obj['size'],
                        'application/gzip',
                        obj['etag'],
                        sample_id,
                        pipeline_id,
                    )
                    logger.info(f"[CONFIRM] Registered {obj['filename']} in minio_objects (pipeline_id={pipeline_id})")

        # Update pipeline paths
        bronze_path = f"{bronze_bucket}/{sample_code}/raw/"
        silver_path = f"genomic-silver/{sample_code}/"
        results_path = f"/results/{sample_code}"

        update_data = PipelineRunUpdate(
            bronze_path=bronze_path,
            silver_path=silver_path
        )
        await self.pipeline_repo.update(pipeline_id, update_data)

        # Enqueue pipeline execution
        from tasks.pipeline_tasks import enqueue_pipeline
        job = enqueue_pipeline(
            pipeline_id=pipeline_id,
            sample_code=sample_code,
            input_dir=bronze_path,
            output_dir=results_path,
            params=parameters or {}
        )
        
        logger.info(f"[CONFIRM] Pipeline enqueued: job_id={job.id}")
        
        # Update pipeline with job_id
        await self.pipeline_repo.update(
            pipeline_id,
            PipelineRunUpdate(job_id=job.id)
        )
        
        total_time = time.time() - start_time
        logger.info(
            f"[CONFIRM] Complete: {total_time:.1f}s total, "
            f"{len(bronze_objects)} files, job_id={job.id}"
        )
        
        return {
            'success': True,
            'pipeline_id': pipeline_id,
            'job_id': job.id,
            'sample_code': sample_code,
            'files_uploaded': len(bronze_objects),
            'message': f'Pipeline queued successfully with job {job.id}',
            'status': 'queued',
            'timing': {
                'total_seconds': round(total_time, 1)
            }
        }
    
    MAX_QUERY_LIMIT = 1000

    async def list_with_samples(
        self,
        status: Optional[str] = None,
        sample_code: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List pipeline runs with sample information (joined query).
        
        Args:
            status: Filter by pipeline status
            sample_code: Filter by sample code
            date_from: Filter by creation date (ISO format)
            date_to: Filter by creation date (ISO format)
            limit: Maximum records
            offset: Pagination offset
            
        Returns:
            List of dictionaries with pipeline run and sample data
        """
        # Cap limit to prevent DoS via unbounded queries
        limit = min(limit, self.MAX_QUERY_LIMIT)
        offset = max(offset, 0)

        query = """
            SELECT
                pr.pipeline_id,
                pr.pipeline_name,
                pr.pipeline_version,
                pr.status,
                pr.parameters,
                pr.results_path,
                pr.log_file_path,
                pr.exit_code,
                pr.error_message,
                pr.runtime_minutes,
                pr.queued_at,
                pr.started_at,
                pr.completed_at,
                pr.created_at,
                pr.sample_name,
                s.sample_id,
                s.sample_code,
                s.sample_type,
                s.collection_date,
                s.sequencing_platform
            FROM pipeline_runs pr
            LEFT JOIN samples s ON pr.sample_id = s.sample_id
        """
        
        where_clauses = []
        params = []
        param_count = 1
        
        if status:
            where_clauses.append(f"pr.status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if sample_code:
            where_clauses.append(f"s.sample_code = ${param_count}")
            params.append(sample_code)
            param_count += 1
        
        if date_from:
            where_clauses.append(f"pr.created_at >= ${param_count}::timestamp")
            params.append(date_from)
            param_count += 1
        
        if date_to:
            where_clauses.append(f"pr.created_at <= ${param_count}::timestamp")
            params.append(date_to)
            param_count += 1
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += f" ORDER BY CASE WHEN pr.status IN ('running', 'queued', 'pending') THEN 0 ELSE 1 END, pr.created_at DESC LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([limit, offset])
        
        async with self.pipeline_repo.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

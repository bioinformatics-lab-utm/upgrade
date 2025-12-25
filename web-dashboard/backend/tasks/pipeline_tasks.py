"""
Redis Queue (RQ) tasks for asynchronous pipeline execution
"""
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import asyncpg
from redis import Redis
from rq import Queue, get_current_job
from rq.job import Job

from config import config

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """Execute Nextflow pipelines asynchronously using Redis Queue"""

    def __init__(self):
        self.nextflow_dir = config.NEXTFLOW_DIR
        self.results_dir = config.RESULTS_DIR
        self.work_dir = config.WORK_DIR
        self.data_dir = config.DATA_DIR

    async def update_pipeline_status(
        self,
        pipeline_id: int,
        status: str,
        error_message: Optional[str] = None,
        exit_code: Optional[int] = None
    ):
        """Update pipeline status in database"""
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)

            await conn.execute("""
                UPDATE pipeline_runs
                SET status = $1::varchar,
                    error_message = $2::text,
                    completed_at = CASE WHEN $1::varchar IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
                    started_at = CASE WHEN $1::varchar = 'running' AND started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END
                WHERE pipeline_id = $3
            """, status, error_message, pipeline_id)

            await conn.close()
            logger.info(f"Pipeline {pipeline_id} status updated to: {status}")

        except Exception as e:
            logger.error(f"Failed to update pipeline status: {e}")

    async def track_progress(
        self,
        pipeline_id: int,
        stage: str,
        step: str,
        status: str,
        progress_percent: int = 0,
        metadata: Optional[Dict] = None
    ):
        """Track pipeline progress in database"""
        try:
            import json
            conn = await asyncpg.connect(config.DATABASE_URL)

            await conn.execute("""
                INSERT INTO pipeline_progress_events
                (pipeline_id, stage, step, status, progress_percent, details)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            """, pipeline_id, stage, step, status, progress_percent, json.dumps(metadata or {}))

            await conn.close()

        except Exception as e:
            logger.error(f"Failed to track progress: {e}")

    def execute_nextflow_pipeline(
        self,
        pipeline_id: int,
        sample_code: str,
        input_dir: Path,
        output_dir: Path,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Execute Nextflow pipeline synchronously
        This function runs in RQ worker process

        Args:
            pipeline_id: Database pipeline ID
            sample_code: Sample identifier
            input_dir: Directory containing input FASTQ files
            output_dir: Directory for results
            params: Additional Nextflow parameters

        Returns:
            Dict with execution results
        """
        job = get_current_job()
        job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
        logger.info(f"Starting pipeline execution for {sample_code} (job: {job_id})")

        try:
            # Update status to running
            import asyncio
            asyncio.run(self.update_pipeline_status(pipeline_id, 'running'))

            # Create work and output directories
            # Files created by rqworker (UID 1003) = nicolaedrabcinski on host
            work_dir = self.work_dir  # Shared across all pipelines for -resume
            work_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create sample-specific input directory (use sample_code for caching across runs)
            sample_work_dir = work_dir / sample_code
            sample_work_dir.mkdir(parents=True, exist_ok=True)

            # CRITICAL FIX: Download files from Bronze layer to /tmp directory
            # /tmp is mounted on both RQ worker and Nextflow containers
            from minio_helper import download_from_bronze, get_minio_client

            local_input_dir = sample_work_dir / 'input'
            local_input_dir.mkdir(parents=True, exist_ok=True)

            asyncio.run(self.track_progress(
                pipeline_id, 'bronze_download', 'Downloading FASTQ from Bronze',
                'started', 15
            ))

            # Download files from MinIO Bronze bucket to work directory
            minio_client = get_minio_client()

            downloaded_files = asyncio.run(download_from_bronze(
                minio_client,
                sample_code,
                str(local_input_dir)
            ))

            logger.info(f"Downloaded {len(downloaded_files)} files from Bronze to {local_input_dir}")

            asyncio.run(self.track_progress(
                pipeline_id, 'bronze_download', f'Downloaded {len(downloaded_files)} files',
                'completed', 20
            ))

            # Use work directory for Nextflow (already in /tmp, accessible to Docker containers)
            input_dir = local_input_dir

            # Build Nextflow command
            nextflow_cmd = [
                'nextflow', 'run',
                str(self.nextflow_dir / 'main.nf'),
                '-profile', 'docker',
                '--input_dir', str(input_dir),
                '--outdir', str(output_dir),
                '-work-dir', str(work_dir),
                '-with-report', str(output_dir / 'nextflow_report.html'),
                '-with-timeline', str(output_dir / 'nextflow_timeline.html'),
                '-with-trace', str(output_dir / 'nextflow_trace.txt'),
                '-resume'
            ]

            # Add custom parameters
            if params:
                for key, value in params.items():
                    if key.startswith('--'):
                        nextflow_cmd.extend([key, str(value)])
                    else:
                        nextflow_cmd.extend([f'--{key}', str(value)])

            logger.info(f"Executing: {' '.join(nextflow_cmd)}")

            # Track execution start
            asyncio.run(self.track_progress(
                pipeline_id, 'execution', 'nextflow_start',
                'in_progress', 0,
                {'command': ' '.join(nextflow_cmd[:10]) + '...'}
            ))

            # Execute Nextflow from work directory (not from read-only /nextflow)
            # Nextflow needs write access to create .nextflow/ directory
            # Set UPGRADE_HOME environment variable for DeepARG database path resolution
            # Set umask to 0 so Docker containers (running as nicolaedrabcinski UID 1003) can write to work dirs
            nextflow_env = os.environ.copy()
            nextflow_env['UPGRADE_HOME'] = '/home/nicolaedrabcinski/upgrade'
            
            # Save old umask and set to 0 (world-writable)
            old_umask = os.umask(0o000)
            try:
                result = subprocess.run(
                    nextflow_cmd,
                    capture_output=True,
                    text=True,
                    timeout=7200,  # 2 hours timeout
                    cwd=str(work_dir),  # Use work_dir instead of nextflow_dir (read-only)
                    env=nextflow_env
                )
            finally:
                # Restore original umask
                os.umask(old_umask)

            # Log Nextflow output immediately
            logger.info(f"Nextflow exit code: {result.returncode}")
            if result.stdout:
                logger.info(f"Nextflow STDOUT:\n{result.stdout}")
            if result.stderr:
                logger.error(f"Nextflow STDERR:\n{result.stderr}")

            # Parse results
            success = result.returncode == 0

            execution_result = {
                'success': success,
                'pipeline_id': pipeline_id,
                'sample_code': sample_code,
                'exit_code': result.returncode,
                'stdout': result.stdout[-5000:],  # Last 5000 chars
                'stderr': result.stderr[-5000:] if result.stderr else None,
                'output_dir': str(output_dir),
                'completed_at': datetime.now().isoformat()
            }

            # Update database status
            if success:
                # Upload results to Silver and Gold layers (simple direct upload for now)
                asyncio.run(self.track_progress(
                    pipeline_id, 'silver_upload', 'Uploading results to Silver layer',
                    'started', 85
                ))

                try:
                    # Simple direct upload of all Nextflow results to Silver layer
                    from pathlib import Path
                    silver_bucket = 'genomic-silver'
                    uploaded_count = 0

                    # Upload all files from output directory
                    for file_path in Path(output_dir).rglob('*'):
                        if file_path.is_file() and not file_path.name.startswith('.'):
                            relative_path = file_path.relative_to(output_dir)
                            object_path = f"{sample_code}/{pipeline_id}/{relative_path}"

                            try:
                                minio_client.client.fput_object(
                                    silver_bucket,
                                    object_path,
                                    str(file_path)
                                )
                                uploaded_count += 1
                                logger.info(f"✓ Uploaded to Silver: {object_path}")
                            except Exception as upload_err:
                                logger.warning(f"Failed to upload {file_path.name}: {upload_err}")

                    logger.info(f"Uploaded {uploaded_count} files to Silver layer")

                    asyncio.run(self.track_progress(
                        pipeline_id, 'silver_upload', f'Uploaded {uploaded_count} files to Silver',
                        'completed', 90
                    ))

                    # Simple Gold layer upload for key results (summary reports)
                    asyncio.run(self.track_progress(
                        pipeline_id, 'gold_curation', 'Uploading key results to Gold',
                        'started', 92
                    ))

                    gold_bucket = 'genomic-gold'
                    gold_count = 0

                    # Upload key report files to Gold layer
                    report_patterns = ['*report.html', '*summary*.txt', '*stats*.txt', '*.log']
                    for pattern in report_patterns:
                        for file_path in Path(output_dir).glob(pattern):
                            if file_path.is_file():
                                gold_path = f"{sample_code}/reports/{file_path.name}"
                                try:
                                    minio_client.client.fput_object(
                                        gold_bucket,
                                        gold_path,
                                        str(file_path)
                                    )
                                    gold_count += 1
                                    logger.info(f"✓ Uploaded to Gold: {gold_path}")
                                except Exception as upload_err:
                                    logger.warning(f"Failed to upload {file_path.name} to Gold: {upload_err}")

                    asyncio.run(self.track_progress(
                        pipeline_id, 'gold_curation', f'Uploaded {gold_count} key results to Gold',
                        'completed', 95
                    ))

                except Exception as e:
                    logger.warning(f"Failed to upload to Silver/Gold layers: {e}", exc_info=True)
                    # Don't fail the pipeline if lakehouse upload fails

                asyncio.run(self.update_pipeline_status(
                    pipeline_id, 'completed', exit_code=0
                ))
                asyncio.run(self.track_progress(
                    pipeline_id, 'execution', 'nextflow_complete',
                    'completed', 100,
                    {'exit_code': 0}
                ))
                logger.info(f"Pipeline {pipeline_id} completed successfully")
            else:
                error_msg = result.stderr[-1000:] if result.stderr else "Unknown error"
                asyncio.run(self.update_pipeline_status(
                    pipeline_id, 'failed', error_message=error_msg, exit_code=result.returncode
                ))
                asyncio.run(self.track_progress(
                    pipeline_id, 'execution', 'nextflow_failed',
                    'failed', 0,
                    {'exit_code': result.returncode, 'error': error_msg}
                ))
                logger.error(f"Pipeline {pipeline_id} failed with exit code {result.returncode}")

            return execution_result

        except subprocess.TimeoutExpired:
            error_msg = "Pipeline execution timed out after 2 hours"
            logger.error(f"Pipeline {pipeline_id}: {error_msg}")

            asyncio.run(self.update_pipeline_status(
                pipeline_id, 'failed', error_message=error_msg
            ))

            return {
                'success': False,
                'pipeline_id': pipeline_id,
                'error': error_msg,
                'timeout': True
            }

        except Exception as e:
            error_msg = f"Pipeline execution error: {str(e)}"
            logger.error(f"Pipeline {pipeline_id}: {error_msg}", exc_info=True)

            asyncio.run(self.update_pipeline_status(
                pipeline_id, 'failed', error_message=error_msg
            ))

            return {
                'success': False,
                'pipeline_id': pipeline_id,
                'error': error_msg
            }


# Initialize executor
executor = PipelineExecutor()


def run_nextflow_pipeline(
    pipeline_id: int,
    sample_code: str,
    input_dir: str,
    output_dir: str,
    params: Optional[Dict] = None
) -> Dict:
    """
    RQ task wrapper for pipeline execution

    This function is called by RQ workers
    """
    return executor.execute_nextflow_pipeline(
        pipeline_id=pipeline_id,
        sample_code=sample_code,
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        params=params or {}
    )


# Helper functions for queue management

def get_redis_connection() -> Redis:
    """Get Redis connection for RQ (no auto-decode to handle binary data)"""
    return Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        password=config.REDIS_PASSWORD,
        decode_responses=False  # Don't auto-decode to handle binary exc_info
    )


def get_pipeline_queue() -> Queue:
    """Get pipeline queue"""
    redis_conn = get_redis_connection()
    return Queue(config.RQ_QUEUE_NAME, connection=redis_conn)


def enqueue_pipeline(
    pipeline_id: int,
    sample_code: str,
    input_dir: str,
    output_dir: str,
    params: Optional[Dict] = None
) -> Job:
    """
    Enqueue a pipeline for async execution

    Returns:
        RQ Job object
    """
    queue = get_pipeline_queue()

    job = queue.enqueue(
        run_nextflow_pipeline,
        pipeline_id=pipeline_id,
        sample_code=sample_code,
        input_dir=input_dir,
        output_dir=output_dir,
        params=params,
        job_timeout=config.RQ_JOB_TIMEOUT,
        result_ttl=86400,  # Keep results for 24 hours
        failure_ttl=86400
    )

    job_id = job.id.decode('utf-8') if isinstance(job.id, bytes) else job.id
    logger.info(f"Pipeline {pipeline_id} enqueued with job ID: {job_id}")
    return job


def get_job_status(job_id: str) -> Dict:
    """Get job status from RQ"""
    redis_conn = get_redis_connection()
    
    # Ensure job_id is string (RQ needs string, not bytes)
    if isinstance(job_id, bytes):
        job_id = job_id.decode('utf-8')
        
    job = Job.fetch(job_id, connection=redis_conn)

    # Safely decode all binary data from Redis
    def safe_decode(value):
        """Safely decode bytes to string"""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='replace')
        return str(value)
    
    # Handle exc_info which might contain binary pickle data
    exc_info = None
    if job.exc_info:
        try:
            exc_info = safe_decode(job.exc_info)
        except Exception as e:
            # Ensure error message is string
            error_msg = safe_decode(e) if isinstance(e, bytes) else str(e)
            exc_info = f"Error info not available: {error_msg}"

    # Decode job_id and status
    job_id_str = safe_decode(job.id)
    status_bytes = job.get_status()
    status_str = safe_decode(status_bytes) if status_bytes else 'unknown'
    
    # Handle result
    result = job.result
    if isinstance(result, bytes):
        result = safe_decode(result)

    return {
        'job_id': job_id_str,
        'status': status_str,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'ended_at': job.ended_at.isoformat() if job.ended_at else None,
        'result': result,
        'exc_info': exc_info
    }


def cancel_job(job_id: str) -> bool:
    """Cancel a running job"""
    try:
        redis_conn = get_redis_connection()
        job = Job.fetch(job_id, connection=redis_conn)
        job.cancel()
        logger.info(f"Job {job_id} cancelled")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel job {job_id}: {e}")
        return False

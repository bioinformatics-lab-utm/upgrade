"""
Pipeline API routes (V2) — single pipeline blueprint.
V1 routes removed; this is now the only pipeline API at /api/pipeline.
"""
from sanic import Blueprint
from sanic.response import json as sanic_json
from datetime import datetime, date
import asyncio
import json
import logging
import time

from auth import protected
from models.pipeline_run import PipelineRunCreate
from utils.error_handling import (
    handle_errors, ValidationError, PipelineConflictError,
    NotFoundError, validate_required_fields, validate_positive_int
)
from tasks import get_job_status, cancel_job

logger = logging.getLogger(__name__)

pipeline_v2_bp = Blueprint('pipeline_v2', url_prefix='/api/pipeline')


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def json_response(data, status=200):
    """Helper to return JSON with datetime serialization"""
    return sanic_json(
        json.loads(json.dumps(data, cls=DateTimeEncoder)),
        status=status
    )


# ==================== UPLOAD FLOW ====================

@pipeline_v2_bp.post("/presigned-upload")
@protected
@handle_errors
async def generate_presigned_urls(request):
    """Generate presigned URLs for direct upload to MinIO."""
    request_start = time.time()

    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        storage_service = services.get_storage_service()

        data = request.json

        sample_code = data.get('sample_code')
        sample_type = data.get('sample_type', 'nanopore')
        collection_date_str = data.get('collection_date', datetime.now().date().isoformat())
        files_info = data.get('files', [])
        pipeline_name = data.get('pipeline_name', 'nextflow_pipeline')
        parameters = data.get('parameters', {})
        notes = data.get('notes', '')

        logger.info(f"[UPLOAD] Presigned URL request for sample_code={sample_code}, files={len(files_info)}")

        if not sample_code:
            return json_response({'error': 'sample_code is required'}, status=400)

        validation = storage_service.validate_file_info(files_info)
        if not validation['valid']:
            return json_response({'error': validation['error']}, status=400)

        try:
            collection_date = datetime.fromisoformat(collection_date_str).date()
        except Exception:
            collection_date = date.today()

        result = await pipeline_service.prepare_upload(
            sample_code=sample_code,
            sample_type=sample_type,
            collection_date=collection_date,
            files_info=files_info,
            pipeline_name=pipeline_name,
            parameters=parameters,
            notes=notes
        )

        request_time = time.time() - request_start
        total_size_mb = validation['total_size'] / 1024 / 1024

        logger.info(
            f"[UPLOAD] Generated {len(result['upload_urls'])} presigned URLs "
            f"for sample {sample_code} ({total_size_mb:.1f} MB) in {request_time:.3f}s"
        )

        uncompressed_count = sum(1 for url in result['upload_urls'] if url['needs_compression'])

        return json_response({
            'success': True,
            'upload_urls': result['upload_urls'],
            'sample_id': result['sample_id'],
            'pipeline_id': result['pipeline_id'],
            'sample_code': result['sample_code'],
            'expires_in': result['expires_in'],
            'message': 'Presigned URLs generated. Upload files directly to MinIO.',
            'optimization_hint': {
                'client_compression': 'Uploading pre-compressed .gz files saves 5-8 minutes of backend processing',
                'uncompressed_files': uncompressed_count,
                'estimated_compression_time': f"{uncompressed_count * 2}-{uncompressed_count * 3} minutes"
            }
        }, status=200)

    except ValueError as e:
        logger.warning(f"[UPLOAD] Validation error: {e}")
        return json_response({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"[UPLOAD] Error generating presigned URLs: {e}", exc_info=True)
        return json_response({'error': 'Failed to generate upload URLs. Check server logs.'}, status=500)


@pipeline_v2_bp.post("/confirm-upload")
@protected
async def confirm_upload(request):
    """Confirm files uploaded to MinIO and start pipeline."""
    request_start = time.time()

    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        data = request.json

        pipeline_id = data.get('pipeline_id')
        sample_id = data.get('sample_id')
        sample_code = data.get('sample_code')
        uploaded_files = data.get('uploaded_files', [])
        parameters = data.get('parameters', {})

        if not all([pipeline_id, sample_id, sample_code]):
            return json_response({
                'error': 'pipeline_id, sample_id, and sample_code are required'
            }, status=400)

        try:
            pipeline_id = int(pipeline_id)
            sample_id = int(sample_id)
        except (ValueError, TypeError):
            return json_response({
                'error': 'pipeline_id and sample_id must be integers'
            }, status=400)

        if not uploaded_files or not isinstance(uploaded_files, list):
            return json_response({'error': 'uploaded_files array is required'}, status=400)

        total_size_mb = sum(f.get('size', 0) for f in uploaded_files) / 1024 / 1024
        logger.info(
            f"[CONFIRM] Request: pipeline={pipeline_id}, sample={sample_code}, "
            f"{len(uploaded_files)} files ({total_size_mb:.1f} MB)"
        )

        result = await pipeline_service.confirm_upload(
            pipeline_id=pipeline_id,
            sample_id=sample_id,
            sample_code=sample_code,
            uploaded_files=uploaded_files,
            parameters=parameters
        )

        request_time = time.time() - request_start
        logger.info(
            f"[CONFIRM] Complete: job {result['job_id']}, "
            f"{result['files_uploaded']} files in {request_time:.1f}s"
        )

        return json_response({
            'success': True,
            'pipeline_id': result['pipeline_id'],
            'job_id': result['job_id'],
            'sample_code': result['sample_code'],
            'files_uploaded': result['files_uploaded'],
            'message': f"Pipeline queued successfully with job {result['job_id']}",
            'status': result['status'],
            'timing': {
                'total_seconds': round(request_time, 1)
            }
        }, status=200)

    except ValueError as e:
        logger.warning(f"[CONFIRM] Validation error: {e}")
        return json_response({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"[CONFIRM] Error: {e}", exc_info=True)
        return json_response({
            'error': 'Failed to confirm upload. Check server logs.'
        }, status=500)


# ==================== PIPELINE RUNS ====================

@pipeline_v2_bp.get("/runs")
@protected
async def get_pipeline_runs(request):
    """Get list of pipeline runs with filtering."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        status = request.args.get('status')
        sample_code = request.args.get('sample_code')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        try:
            limit = min(int(request.args.get('limit', 100)), 10000)
            offset = max(int(request.args.get('offset', 0)), 0)
        except (ValueError, TypeError):
            return json_response({'error': 'Invalid limit or offset'}, status=400)

        if date_from:
            try:
                datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return json_response({'error': 'Invalid date_from format'}, status=400)

        if date_to:
            try:
                datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return json_response({'error': 'Invalid date_to format'}, status=400)

        runs = await pipeline_service.list_with_samples(
            status=status,
            sample_code=sample_code,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset
        )

        total = await pipeline_service.count_by_status(status) if status else await pipeline_service.pipeline_repo.count()

        return json_response({
            'runs': runs,
            'total': total,
            'limit': limit,
            'offset': offset
        }, status=200)

    except Exception as e:
        logger.error(f"Error listing pipeline runs: {e}")
        return json_response({'error': 'Internal server error'}, status=500)


@pipeline_v2_bp.get("/runs/<pipeline_id:int>")
@protected
async def get_pipeline_run(request, pipeline_id: int):
    """Get single pipeline run by ID."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        run = await pipeline_service.get_pipeline_run(pipeline_id)

        if not run:
            return json_response({'error': 'Pipeline run not found'}, status=404)

        return json_response(run.model_dump(), status=200)

    except Exception as e:
        logger.error(f"Error fetching pipeline run {pipeline_id}: {e}")
        return json_response({'error': 'Internal server error'}, status=500)


@pipeline_v2_bp.put("/runs/<pipeline_id:int>/status")
@protected
async def update_pipeline_status(request, pipeline_id: int):
    """Update pipeline run status."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        data = request.json
        status = data.get('status')

        if not status:
            return json_response({'error': 'status is required'}, status=400)

        success = await pipeline_service.update_status(
            pipeline_id,
            status,
            error_message=data.get('error_message'),
            exit_code=data.get('exit_code')
        )

        if not success:
            return json_response({'error': 'Pipeline run not found'}, status=404)

        return json_response({
            'success': True,
            'pipeline_id': pipeline_id,
            'status': status
        }, status=200)

    except ValueError as e:
        return json_response({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error updating pipeline status: {e}")
        return json_response({'error': 'Internal server error'}, status=500)


# ==================== PROGRESS TRACKING ====================

@pipeline_v2_bp.get("/runs/<pipeline_id:int>/progress")
@protected
async def get_pipeline_progress(request, pipeline_id: int):
    """Get real-time progress events for a pipeline run."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        pool = pipeline_service.pipeline_repo.pool

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT event_id, stage, step, status, progress_percent, details, created_at
                FROM pipeline_progress_events
                WHERE pipeline_id = $1
                ORDER BY created_at ASC
            """, pipeline_id)

        events = [
            {
                'event_id': row['event_id'],
                'stage': row['stage'],
                'step': row['step'],
                'status': row['status'],
                'progress_percent': float(row['progress_percent']) if row['progress_percent'] else None,
                'details': row['details'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None
            }
            for row in rows
        ]

        return json_response({
            'pipeline_id': pipeline_id,
            'events': events,
            'total_events': len(events)
        })

    except Exception as e:
        logger.error(f"Error fetching pipeline progress: {e}", exc_info=True)
        return json_response({'error': str(e)}, status=500)


# ==================== STATISTICS ====================

@pipeline_v2_bp.get("/stats")
@protected
async def get_pipeline_stats(request):
    """Get pipeline statistics."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        stats = await pipeline_service.get_statistics()

        # Build flat structure expected by frontend
        by_status = {s: v.get('count', 0) for s, v in stats.items()} if isinstance(list(stats.values())[0], dict) else stats
        total = sum(by_status.values())

        return json_response({
            'statistics': stats,
            'total_runs': total,
            'running':   by_status.get('running', 0),
            'queued':    by_status.get('queued', 0) + by_status.get('pending', 0),
            'completed': by_status.get('completed', 0),
            'failed':    by_status.get('failed', 0),
            'cancelled': by_status.get('cancelled', 0),
            'timestamp': datetime.utcnow().isoformat()
        }, status=200)

    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        return json_response({'error': 'Internal server error'}, status=500)


# ==================== SUBMISSION ====================

@pipeline_v2_bp.post("/submit")
@protected
async def submit_pipeline(request):
    """
    Submit pipeline run for execution.
    For file uploads, use /presigned-upload + /confirm-upload flow.
    """
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        data = request.json

        sample_code = data.get('sample_code')
        pipeline_name = data.get('pipeline_name', 'nextflow_pipeline')
        parameters = data.get('parameters', {})

        if not sample_code:
            return json_response({'error': 'sample_code is required'}, status=400)

        logger.info(f"[SUBMIT] Pipeline submission for sample {sample_code}")

        sample_service = services.get_sample_service()
        sample = await sample_service.get_sample_by_code(sample_code)

        if not sample:
            return json_response({'error': f'Sample {sample_code} not found'}, status=404)

        from pathlib import Path

        results_path = f"/results/{sample_code}"
        log_path = f"{results_path}/nextflow.log"
        Path(results_path).mkdir(parents=True, exist_ok=True, mode=0o777)

        pipeline_create = PipelineRunCreate(
            sample_id=sample.sample_id,
            sample_name=sample_code,
            pipeline_name=pipeline_name,
            parameters=parameters,
            results_path=results_path,
            log_path=log_path,
            status='queued'
        )

        pipeline_id = await pipeline_service.create_pipeline_run(pipeline_create)

        job_id = f"job_{pipeline_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        from models.pipeline_run import PipelineRunUpdate
        await pipeline_service.pipeline_repo.update(
            pipeline_id,
            PipelineRunUpdate(job_id=job_id)
        )

        logger.info(f"[SUBMIT] Created pipeline {pipeline_id}, job {job_id}")

        return json_response({
            'success': True,
            'pipeline_id': pipeline_id,
            'job_id': job_id,
            'sample_id': sample.sample_id,
            'sample_code': sample_code,
            'status': 'queued',
            'message': f'Pipeline {pipeline_id} queued successfully'
        }, status=201)

    except Exception as e:
        logger.error(f"[SUBMIT] Error: {e}", exc_info=True)
        return json_response({'error': 'Pipeline submission failed'}, status=500)


# ==================== JOB STATUS & CONTROL ====================

@pipeline_v2_bp.get("/job/<job_id:str>/status")
@protected
async def get_job_status_endpoint(request, job_id: str):
    """Get RQ job status."""
    try:
        status = get_job_status(job_id)
        return json_response(status, status=200)
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {e}")
        return json_response({'error': str(e), 'job_id': job_id}, status=404)


@pipeline_v2_bp.post("/job/<job_id:str>/cancel")
@protected
async def cancel_job_endpoint(request, job_id: str):
    """Cancel a queued/running job."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        pool = pipeline_service.pipeline_repo.pool

        async with pool.acquire() as conn:
            pipeline_run = await conn.fetchrow(
                "SELECT pipeline_id, status FROM pipeline_runs WHERE job_id = $1",
                job_id
            )

        if not pipeline_run:
            return json_response({
                'success': False,
                'job_id': job_id,
                'message': 'Pipeline not found'
            }, status=404)

        current_status = pipeline_run['status']
        if current_status not in ('queued', 'running'):
            return json_response({
                'success': False,
                'job_id': job_id,
                'message': f'Cannot cancel pipeline in status: {current_status}'
            }, status=400)

        success = cancel_job(job_id)

        if success:
            await pipeline_service.update_status(
                pipeline_run['pipeline_id'],
                'cancelled'
            )

            return json_response({
                'success': True,
                'job_id': job_id,
                'message': f'Job {job_id} cancelled successfully'
            }, status=200)
        else:
            return json_response({
                'success': False,
                'job_id': job_id,
                'message': 'Job could not be cancelled'
            }, status=400)

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return json_response({'error': str(e)}, status=500)


@pipeline_v2_bp.post("/<pipeline_id:int>/cancel-stale")
@protected
async def cancel_stale_pipeline(request, pipeline_id: int):
    """
    Cancel a pipeline stuck in 'queued' without a job_id.
    Called by the frontend when presigned upload fails mid-way.
    """
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        pool = pipeline_service.pipeline_repo.pool

        async with pool.acquire() as conn:
            result = await conn.fetchval("""
                UPDATE pipeline_runs
                SET status = 'failed',
                    error_message = 'Upload interrupted - pipeline never started',
                    completed_at = CURRENT_TIMESTAMP
                WHERE pipeline_id = $1
                  AND status = 'queued'
                  AND job_id IS NULL
                RETURNING pipeline_id
            """, pipeline_id)

        if result:
            logger.info(f"Cancelled stale pipeline {pipeline_id} (no job_id)")
            return json_response({'success': True, 'pipeline_id': pipeline_id})
        else:
            return json_response(
                {'success': False, 'message': 'Pipeline not found or already started'},
                status=404
            )
    except Exception as e:
        logger.error(f"Error cancelling stale pipeline {pipeline_id}: {e}")
        return json_response({'error': str(e)}, status=500)


# ==================== LOGS & PROCESSES ====================

@pipeline_v2_bp.get("/runs/<pipeline_id:int>/log")
@protected
async def get_pipeline_log(request, pipeline_id: int):
    """Get execution log."""
    try:
        from pathlib import Path
        import subprocess

        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()

        try:
            lines = min(int(request.args.get('lines', 100)), 10000)
            lines = max(lines, 1)
        except (ValueError, TypeError):
            return json_response({'error': 'Invalid lines parameter'}, status=400)

        run = await pipeline_service.get_pipeline_run(pipeline_id)
        if not run:
            return json_response({'error': 'Pipeline not found'}, status=404)

        log_path = run.log_file_path
        if not log_path or not Path(log_path).exists():
            return json_response({
                'pipeline_id': pipeline_id,
                'log': 'Log file not available yet',
                'lines': 0
            }, status=200)

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ['tail', '-n', str(lines), log_path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )
            log_content = result.stdout
        except Exception as e:
            log_content = f"Error reading log: {str(e)}"

        return json_response({
            'pipeline_id': pipeline_id,
            'log': log_content,
            'lines': len(log_content.splitlines())
        }, status=200)

    except Exception as e:
        logger.error(f"Error reading log for pipeline {pipeline_id}: {e}")
        return json_response({'error': 'Failed to read log'}, status=500)


@pipeline_v2_bp.get("/runs/<pipeline_id:int>/processes")
@protected
async def get_pipeline_processes(request, pipeline_id: int):
    """Get Nextflow process details."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        pool = pipeline_service.pipeline_repo.pool

        async with pool.acquire() as conn:
            execution_id = await conn.fetchval(
                "SELECT nextflow_execution_id FROM pipeline_runs WHERE pipeline_id = $1",
                pipeline_id
            )

            if not execution_id:
                return json_response({
                    'pipeline_id': pipeline_id,
                    'processes': [],
                    'message': 'No Nextflow execution found'
                }, status=200)

            query = """
                SELECT
                    process_id, process_name, task_id, status, exit_code,
                    start_time, complete_time,
                    EXTRACT(EPOCH FROM duration) as duration_seconds,
                    cpu_usage, peak_memory_mb, peak_vmem_mb,
                    disk_read_mb, disk_write_mb,
                    container_image, work_directory, attempt,
                    error_action, input_files, output_files
                FROM nextflow_processes
                WHERE execution_id = $1
                ORDER BY start_time ASC
            """

            rows = await conn.fetch(query, execution_id)

        processes = [
            {
                'id': row['process_id'],
                'name': row['process_name'],
                'task_id': row['task_id'],
                'status': row['status'],
                'exit_code': row['exit_code'],
                'start_time': row['start_time'].isoformat() if row['start_time'] else None,
                'complete_time': row['complete_time'].isoformat() if row['complete_time'] else None,
                'duration_seconds': float(row['duration_seconds']) if row['duration_seconds'] else None,
                'cpu_hours': float(row['cpu_usage']) if row['cpu_usage'] else None,
                'memory_mb': float(row['peak_memory_mb']) if row['peak_memory_mb'] else None,
                'container': row['container_image'],
                'work_dir': row['work_directory']
            }
            for row in rows
        ]

        return json_response({
            'pipeline_id': pipeline_id,
            'execution_id': execution_id,
            'total_processes': len(processes),
            'processes': processes
        }, status=200)

    except Exception as e:
        logger.error(f"Error fetching processes for pipeline {pipeline_id}: {e}")
        return json_response({'error': 'Failed to fetch processes'}, status=500)


# ==================== CLEANUP ====================

@pipeline_v2_bp.post("/cleanup-stuck")
@protected
async def cleanup_stuck_pipelines(request):
    """Cleanup stuck pipelines."""
    try:
        services = request.app.ctx.services
        pipeline_service = services.get_pipeline_service()
        pool = pipeline_service.pipeline_repo.pool

        try:
            hours = int(request.args.get('hours', 2))
            if hours < 1 or hours > 168:
                return json_response({'error': 'hours must be between 1 and 168'}, status=400)
        except (ValueError, TypeError):
            return json_response({'error': 'Invalid hours parameter'}, status=400)

        dry_run = request.args.get('dry_run', 'false').lower() == 'true'

        query = """
            SELECT pipeline_id, status, job_id, queued_at,
                   EXTRACT(EPOCH FROM (NOW() - queued_at))/3600 as hours_stuck
            FROM pipeline_runs
            WHERE status IN ('queued', 'running')
              AND queued_at < NOW() - INTERVAL '1 hour' * $1
            ORDER BY queued_at
        """

        async with pool.acquire() as conn:
            stuck_pipelines = await conn.fetch(query, hours)

        if dry_run:
            return json_response({
                'dry_run': True,
                'stuck_count': len(stuck_pipelines),
                'pipelines': [
                    {
                        'pipeline_id': row['pipeline_id'],
                        'status': row['status'],
                        'hours_stuck': float(row['hours_stuck']),
                        'job_id': row['job_id']
                    }
                    for row in stuck_pipelines
                ]
            }, status=200)

        updated_count = 0
        for row in stuck_pipelines:
            hours_stuck = float(row['hours_stuck'])
            error_msg = f'Pipeline timed out after {hours_stuck:.1f} hours'

            await pipeline_service.mark_as_failed(
                row['pipeline_id'],
                error_msg,
                exit_code=-1
            )

            if row['job_id']:
                try:
                    cancel_job(row['job_id'])
                except Exception as e:
                    logger.warning(f"Could not cancel job {row['job_id']}: {e}")

            updated_count += 1
            logger.info(f"Marked pipeline {row['pipeline_id']} as failed (stuck {hours_stuck:.1f}h)")

        return json_response({
            'success': True,
            'cleaned_up': updated_count,
            'threshold_hours': hours,
            'message': f'Cleaned up {updated_count} stuck pipelines'
        }, status=200)

    except Exception as e:
        logger.error(f"Error cleaning up stuck pipelines: {e}")
        return json_response({'error': str(e)}, status=500)

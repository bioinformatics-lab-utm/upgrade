"""
Pipeline Management Routes
Genomic pipeline upload, monitoring, and management
Synchronized with Streamlit NextflowRunner and real DB schema
"""
from sanic import Blueprint
from sanic.response import json, file as file_response
from sanic.exceptions import ServerError, NotFound
import os
import json as json_lib
from datetime import datetime, date
from pathlib import Path
import asyncio
import subprocess
import logging
import re
from minio_helper import get_minio_client, save_minio_object_to_db, get_or_create_bucket, upload_to_bronze, download_from_bronze, upload_to_silver, curate_gold_layer

# Import Redis Queue tasks
from tasks import enqueue_pipeline, get_job_status, cancel_job, get_pipeline_queue

# Import FASTQ validation
from utils import validate_fastq_files, FASTQValidationError

# Import authentication
from auth import protected

pipeline_bp = Blueprint('pipeline', url_prefix='/api/pipeline')
logger = logging.getLogger(__name__)

# MinIO configuration
MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'genomic-data')


# ==================== PROGRESS TRACKING ====================

async def track_progress(conn, pipeline_id, stage, step, status='in_progress', progress_percent=0, details=None):
    """
    Track pipeline progress in real-time
    
    Args:
        conn: Database connection
        pipeline_id: Pipeline run ID
        stage: High-level stage (bronze_upload, nextflow_exec, silver_upload, gold_curation, cleanup)
        step: Detailed step description
        status: started, in_progress, completed, failed
        progress_percent: 0-100
        details: Dict with additional context
    """
    query = """
        INSERT INTO pipeline_progress_events 
        (pipeline_id, stage, step, status, progress_percent, details)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING event_id
    """
    
    details_json = json_lib.dumps(details or {})
    
    try:
        event_id = await conn.fetchval(
            query, pipeline_id, stage, step, status, progress_percent, details_json
        )
        logger.info(f"[Pipeline {pipeline_id}] {stage} > {step} ({progress_percent}%)")
        return event_id
    except Exception as e:
        logger.error(f"Failed to track progress: {e}")
        return None


async def fetch_pipeline_progress_events(conn, pipeline_id):
    """
    Get all progress events for a pipeline

    Returns:
        List of progress events ordered by time
    """
    query = """
        SELECT
            event_id,
            stage,
            step,
            status,
            progress_percent,
            details,
            created_at
        FROM pipeline_progress_events
        WHERE pipeline_id = $1
        ORDER BY created_at ASC
    """

    rows = await conn.fetch(query, pipeline_id)

    return [
        {
            'event_id': row['event_id'],
            'stage': row['stage'],
            'step': row['step'],
            'status': row['status'],
            'progress_percent': row['progress_percent'],
            'details': row['details'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        }
        for row in rows
    ]


# ==================== HELPER FUNCTIONS ====================

async def get_db_pool(app):
    """Get database connection pool from app context"""
    return app.ctx.db_pool


async def create_sample_record(conn, sample_code, sample_type, collection_date, notes=""):
    """Create a new sample record in the database or return existing one"""
    # Check if sample already exists
    check_query = "SELECT sample_id FROM samples WHERE sample_code = $1"
    existing_id = await conn.fetchval(check_query, sample_code)
    
    if existing_id:
        logger.info(f"Sample {sample_code} already exists with ID {existing_id}, reusing it")
        return existing_id
    
    # Create new sample
    query = """
        INSERT INTO samples (
            sample_code, 
            collection_date, 
            sample_type, 
            sequencing_platform,
            notes,
            status
        ) VALUES ($1, $2, $3, $4, $5, 'collected')
        RETURNING sample_id
    """
    
    # Map sample_type to sequencing_platform
    platform_map = {
        'nanopore': 'Oxford Nanopore',
        'illumina': 'Illumina',
        'pacbio': 'PacBio'
    }
    platform = platform_map.get(sample_type, 'Oxford Nanopore')
    
    sample_id = await conn.fetchval(
        query, 
        sample_code, 
        collection_date, 
        sample_type, 
        platform,
        notes
    )
    return sample_id


async def create_pipeline_run(conn, sample_id, pipeline_name, parameters, results_path, log_path):
    """Create a new pipeline run record"""
    query = """
        INSERT INTO pipeline_runs (
            sample_id,
            pipeline_name,
            pipeline_version,
            parameters,
            results_path,
            log_file_path,
            status,
            queued_at,
            started_at
        ) VALUES ($1, $2, $3, $4, $5, $6, 'queued', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING pipeline_id
    """
    
    pipeline_id = await conn.fetchval(
        query,
        sample_id,
        pipeline_name,
        '1.0',  # pipeline_version
        json_lib.dumps(parameters),
        results_path,
        log_path
    )
    return pipeline_id


async def create_nextflow_execution(conn, pipeline_id, sample_code, work_dir, publish_dir, 
                                    trace_path, report_path, timeline_path, params):
    """Create a Nextflow execution record and link to pipeline run"""
    # First, check if workflow already exists
    check_workflow = """
        SELECT workflow_id FROM nextflow_workflows 
        WHERE workflow_name = $1 AND workflow_version = $2
        LIMIT 1
    """
    workflow_id = await conn.fetchval(
        check_workflow,
        'UPGRADE_Genomic_Pipeline',
        '1.0'
    )
    
    # If not exists, create new workflow definition
    if not workflow_id:
        workflow_query = """
            INSERT INTO nextflow_workflows (
                workflow_name,
                workflow_version,
                description,
                nextflow_version,
                workflow_script_path,
                is_active
            ) VALUES ($1, $2, $3, $4, $5, true)
            RETURNING workflow_id
        """
        workflow_id = await conn.fetchval(
            workflow_query,
            'UPGRADE_Genomic_Pipeline',
            '1.0',
            'Environmental genomic surveillance with ONT sequencing',
            '25.10.0',
            '/nextflow/main.nf'
        )
    
    # Create execution record
    exec_query = """
        INSERT INTO nextflow_executions (
            workflow_id,
            execution_name,
            nextflow_run_name,
            work_directory,
            publish_directory,
            trace_file_path,
            report_file_path,
            timeline_file_path,
            status,
            start_time,
            params,
            nextflow_config
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'submitted', CURRENT_TIMESTAMP, $9, $10)
        RETURNING execution_id
    """
    
    execution_id = await conn.fetchval(
        exec_query,
        workflow_id,
        f"pipeline_{pipeline_id}_{sample_code}",
        f"nxf_{sample_code}",  # Nextflow auto-generates this
        work_dir,
        publish_dir,
        trace_path,
        report_path,
        timeline_path,
        json_lib.dumps(params),
        json_lib.dumps({'profile': 'docker'})
    )
    
    # Link execution to pipeline run
    update_query = """
        UPDATE pipeline_runs 
        SET nextflow_execution_id = $1
        WHERE pipeline_id = $2
    """
    await conn.execute(update_query, execution_id, pipeline_id)
    
    logger.info(f"Created Nextflow execution {execution_id} for pipeline {pipeline_id}")
    return execution_id


async def update_pipeline_status(conn, pipeline_id, status, error_message=None, exit_code=None):
    """Update pipeline run status"""
    query = """
        UPDATE pipeline_runs 
        SET status = $2::VARCHAR, 
            error_message = $3,
            exit_code = $4,
            completed_at = CASE WHEN $2::VARCHAR IN ('completed', 'failed', 'cancelled') 
                               THEN CURRENT_TIMESTAMP 
                               ELSE completed_at 
                          END
        WHERE pipeline_id = $1
    """
    await conn.execute(query, pipeline_id, status, error_message, exit_code)


async def update_nextflow_execution_status(conn, execution_id, status, exit_status=None, 
                                          error_message=None, cpu_hours=None, peak_memory=None):
    """Update Nextflow execution status and metrics"""
    query = """
        UPDATE nextflow_executions
        SET status = $2::VARCHAR,
            complete_time = CASE WHEN $2::VARCHAR IN ('succeeded', 'failed', 'cancelled')
                               THEN CURRENT_TIMESTAMP
                               ELSE complete_time
                          END,
            duration = CASE WHEN $2::VARCHAR IN ('succeeded', 'failed', 'cancelled')
                          THEN CURRENT_TIMESTAMP - start_time
                          ELSE duration
                     END,
            success = CASE WHEN $2::VARCHAR = 'succeeded' THEN true
                          WHEN $2::VARCHAR = 'failed' THEN false
                          ELSE success
                     END,
            exit_status = $3,
            error_message = $4,
            total_cpu_hours = $5,
            peak_memory_gb = $6
        WHERE execution_id = $1
    """
    await conn.execute(query, execution_id, status, exit_status, error_message, 
                      cpu_hours, peak_memory)


async def parse_nextflow_trace(trace_file_path, execution_id, conn):
    """
    Parse Nextflow trace.txt file and create process records
    
    Trace format (TSV with headers):
    task_id, hash, native_id, process, tag, name, status, exit, module, container,
    cpus, time, disk, memory, attempt, submit, start, complete, duration, realtime,
    queue, %cpu, %mem, rss, vmem, peak_rss, peak_vmem, rchar, wchar, syscr, syscw,
    read_bytes, write_bytes, vol_ctxt, inv_ctxt, workdir, scratch, error_action
    """
    if not Path(trace_file_path).exists():
        logger.warning(f"Trace file not found: {trace_file_path}")
        return 0
    
    import csv
    from datetime import datetime
    
    processes_created = 0
    
    try:
        with open(trace_file_path, 'r') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            for row in reader:
                # Parse timestamps
                submit_time = None
                start_time = None
                complete_time = None
                
                try:
                    if row.get('submit'):
                        submit_time = datetime.fromisoformat(row['submit'].replace('Z', '+00:00'))
                    if row.get('start'):
                        start_time = datetime.fromisoformat(row['start'].replace('Z', '+00:00'))
                    if row.get('complete'):
                        complete_time = datetime.fromisoformat(row['complete'].replace('Z', '+00:00'))
                except Exception as e:
                    logger.warning(f"Error parsing timestamps: {e}")
                
                # Calculate duration
                duration = None
                if row.get('duration'):
                    # Duration is in milliseconds
                    try:
                        duration_ms = int(row['duration'])
                        duration = f"{duration_ms / 1000.0} seconds"
                    except Exception:
                        pass
                
                # Parse memory
                peak_memory_mb = None
                if row.get('peak_rss'):
                    try:
                        # peak_rss is in bytes
                        peak_memory_mb = int(row['peak_rss']) / (1024 * 1024)
                    except Exception:
                        pass
                
                peak_vmem_mb = None
                if row.get('peak_vmem'):
                    try:
                        peak_vmem_mb = int(row['peak_vmem']) / (1024 * 1024)
                    except Exception:
                        pass
                
                # Parse CPU usage
                cpu_usage = None
                if row.get('realtime'):
                    try:
                        # realtime is in milliseconds, cpus is core count
                        realtime_hours = int(row['realtime']) / (1000.0 * 3600.0)
                        cpus = int(row.get('cpus', 1))
                        cpu_usage = realtime_hours * cpus
                    except Exception:
                        pass
                
                # Parse disk I/O
                disk_read_mb = None
                disk_write_mb = None
                if row.get('read_bytes'):
                    try:
                        disk_read_mb = int(row['read_bytes']) / (1024 * 1024)
                    except Exception:
                        pass
                if row.get('write_bytes'):
                    try:
                        disk_write_mb = int(row['write_bytes']) / (1024 * 1024)
                    except Exception:
                        pass
                
                # Insert process record
                query = """
                    INSERT INTO nextflow_processes (
                        execution_id,
                        process_name,
                        task_id,
                        status,
                        exit_code,
                        start_time,
                        complete_time,
                        duration,
                        cpu_usage,
                        peak_memory_mb,
                        peak_vmem_mb,
                        disk_read_mb,
                        disk_write_mb,
                        container_image,
                        container_hash,
                        work_directory,
                        error_action,
                        attempt
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::interval, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                """
                
                await conn.execute(
                    query,
                    execution_id,
                    row.get('process', 'UNKNOWN'),
                    row.get('task_id'),
                    row.get('status', 'UNKNOWN').lower(),
                    int(row.get('exit', 0)) if row.get('exit') else None,
                    start_time,
                    complete_time,
                    duration,
                    cpu_usage,
                    peak_memory_mb,
                    peak_vmem_mb,
                    disk_read_mb,
                    disk_write_mb,
                    row.get('container'),
                    row.get('hash'),
                    row.get('workdir'),
                    row.get('error_action', 'terminate'),
                    int(row.get('attempt', 1))
                )
                
                processes_created += 1
        
        logger.info(f"Parsed {processes_created} processes from trace file")
        return processes_created
        
    except Exception as e:
        logger.error(f"Error parsing trace file: {e}", exc_info=True)
        return 0


# ==================== PIPELINE SUBMISSION ====================

@pipeline_bp.post("/presigned-upload")
async def generate_presigned_urls(request):
    """
    Generate presigned URLs for direct upload to MinIO
    
    Expects JSON with:
    - sample_code: str
    - sample_type: str
    - collection_date: str (ISO format)
    - files: [{'name': str, 'size': int}]
    - pipeline_name: str (optional)
    - parameters: dict (optional)
    - notes: str (optional)
    
    Returns:
    - upload_urls: [{filename, presigned_url, object_path}]
    - upload_id: str (for tracking)
    - sample_id: int
    """
    import time
    request_start = time.time()
    
    try:
        db_pool = await get_db_pool(request.app)
        data = request.json
        
        logger.info(f"[UPLOAD] Presigned URL request started for sample_code={data.get('sample_code')}, files={len(data.get('files', []))}")
        
        sample_code = data.get('sample_code')
        sample_type = data.get('sample_type', 'nanopore')
        
        # Validate sample_type
        valid_sample_types = ['nanopore', 'illumina', 'pacbio']
        if sample_type not in valid_sample_types:
            return json({'error': f'Invalid sample_type. Must be one of: {valid_sample_types}'}, status=400)
        collection_date_str = data.get('collection_date', datetime.now().date().isoformat())
        files_info = data.get('files', [])
        pipeline_name = data.get('pipeline_name', 'nextflow_pipeline')
        parameters = data.get('parameters', {})
        notes = data.get('notes', '')
        
        # Validate sample_code
        if not sample_code:
            return json({'error': 'sample_code is required'}, status=400)
        
        # Prevent path traversal and validate sample_code format
        import re
        if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', sample_code):
            return json({'error': 'Invalid sample_code format. Use only alphanumeric, underscore, and hyphen (max 100 chars)'}, status=400)
        
        # Validate files array
        if not files_info:
            return json({'error': 'files array is required'}, status=400)
        
        # Limit number of files to prevent DoS
        if len(files_info) > 50:
            return json({'error': 'Maximum 50 files per upload'}, status=400)
        
        # Validate file sizes
        max_file_size = 50 * 1024 * 1024 * 1024  # 50 GB per file
        total_size = 0
        for file_info in files_info:
            if not isinstance(file_info, dict) or 'name' not in file_info or 'size' not in file_info:
                return json({'error': 'Each file must have name and size fields'}, status=400)
            
            file_size = file_info.get('size', 0)
            if file_size <= 0 or file_size > max_file_size:
                return json({'error': f'File {file_info["name"]}: size must be between 1 byte and 50GB'}, status=400)
            
            total_size += file_size
        
        # Limit total upload size
        if total_size > 500 * 1024 * 1024 * 1024:  # 500 GB total
            return json({'error': 'Total upload size exceeds 500GB limit'}, status=400)
        
        # Parse collection date
        try:
            collection_date = datetime.fromisoformat(collection_date_str).date()
        except Exception:
            collection_date = date.today()
        
        # Initialize MinIO client
        minio_client = get_minio_client()
        bronze_bucket = 'genomic-bronze'
        
        # Create sample and pipeline records
        async with db_pool.acquire() as conn:
            # Create sample
            sample_id = await create_sample_record(
                conn, sample_code, sample_type, collection_date, notes
            )
            
            # Create pipeline run
            results_path = f"/results/{sample_code}"
            log_path = f"{results_path}/nextflow.log"
            Path(results_path).mkdir(parents=True, exist_ok=True)
            
            pipeline_id = await create_pipeline_run(
                conn, sample_id, pipeline_name, parameters,
                results_path, log_path
            )
        
        # Generate presigned URLs for each file
        upload_urls = []
        for file_info in files_info:
            filename = file_info['name']
            
            # Sanitize filename to prevent path traversal
            import os
            filename = os.path.basename(filename)  # Remove any directory components
            filename = filename.replace('\x00', '')  # Remove null bytes
            
            # Validate filename
            if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
                return json({'error': f'Invalid filename: {file_info["name"]}. Use only alphanumeric, underscore, dot, and hyphen'}, status=400)
            
            if len(filename) > 255:
                return json({'error': f'Filename too long: {filename}'}, status=400)
            
            # Validate file extension
            valid_extensions = ['.fastq', '.fq', '.fastq.gz', '.fq.gz', '.fasta', '.fa', '.fna']
            if not any(filename.endswith(ext) for ext in valid_extensions):
                return json({'error': f'Invalid file extension for {filename}. Allowed: {valid_extensions}'}, status=400)
            
            # Upload with original filename - compression will happen on backend if needed
            object_path = f"{sample_code}/raw/{filename}"
            
            presigned_url = minio_client.generate_presigned_put_url(
                bronze_bucket,
                object_path,
                expires_seconds=3600  # 1 hour
            )
            
            # Replace internal MinIO endpoint with nginx proxy path
            # Use relative /minio/ path to proxy through frontend nginx
            from config import config
            import urllib.parse
            parsed = urllib.parse.urlparse(presigned_url)
            # Keep query string, change scheme+host to relative path through nginx
            external_url = f'/minio{parsed.path}?{parsed.query}'
            
            upload_urls.append({
                'filename': filename,
                'presigned_url': external_url,
                'object_path': object_path,
                'size': file_info.get('size', 0),
                'needs_compression': not filename.endswith('.gz')
            })
        
        request_time = time.time() - request_start
        total_size_mb = sum(file_info.get('size', 0) for file_info in files_info) / 1024 / 1024
        logger.info(f"[UPLOAD] Generated {len(upload_urls)} presigned URLs for sample {sample_code} ({total_size_mb:.1f} MB total) in {request_time:.3f}s")
        
        return json({
            'success': True,
            'upload_urls': upload_urls,
            'sample_id': sample_id,
            'pipeline_id': pipeline_id,
            'sample_code': sample_code,
            'expires_in': 3600,
            'message': 'Presigned URLs generated. Upload files directly to MinIO.',
            'optimization_hint': {
                'client_compression': 'Uploading pre-compressed .gz files saves 5-8 minutes of backend processing time',
                'uncompressed_files': sum(1 for url in upload_urls if url['needs_compression']),
                'estimated_compression_time': f"{sum(1 for url in upload_urls if url['needs_compression']) * 2}-{sum(1 for url in upload_urls if url['needs_compression']) * 3} minutes"
            }
        })
        
    except Exception as e:
        logger.error(f"Error generating presigned URLs: {str(e)}", exc_info=True)
        return json({'error': 'Failed to generate upload URLs. Check server logs for details.'}, status=500)


@pipeline_bp.post("/confirm-upload")
async def confirm_upload(request):
    """
    Confirm files uploaded to MinIO and start pipeline
    
    Expects JSON with:
    - pipeline_id: int
    - sample_id: int
    - sample_code: str
    - uploaded_files: [{'filename', 'object_path', 'size', 'etag'}]
    """
    import time
    confirm_start = time.time()
    
    try:
        request_start_time = time.time()
        logger.info(f"[UPLOAD] Starting confirm-upload request")
        
        db_pool = await get_db_pool(request.app)
        data = request.json
        
        pipeline_id = data.get('pipeline_id')
        sample_id = data.get('sample_id')
        sample_code = data.get('sample_code')
        uploaded_files = data.get('uploaded_files', [])
        parameters = data.get('parameters', {})
        
        logger.info(f"[UPLOAD] Request params: pipeline_id={pipeline_id}, sample_id={sample_id}, sample_code={sample_code}, files={len(uploaded_files)}")
        
        total_uploaded_mb = sum(f.get('size', 0) for f in uploaded_files) / 1024 / 1024
        logger.info(f"[UPLOAD] Confirm-upload started: pipeline_id={pipeline_id}, sample={sample_code}, files={len(uploaded_files)} ({total_uploaded_mb:.1f} MB)")
        
        if not all([pipeline_id, sample_id, sample_code]):
            return json({'error': 'pipeline_id, sample_id, and sample_code are required'}, status=400)
        
        # Validate types
        try:
            pipeline_id = int(pipeline_id)
            sample_id = int(sample_id)
        except (ValueError, TypeError):
            return json({'error': 'pipeline_id and sample_id must be integers'}, status=400)
        
        # Validate sample_code again
        if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', sample_code):
            return json({'error': 'Invalid sample_code format'}, status=400)
        
        # Validate uploaded_files
        if not uploaded_files or not isinstance(uploaded_files, list):
            return json({'error': 'uploaded_files array is required'}, status=400)
        
        if len(uploaded_files) > 50:
            return json({'error': 'Maximum 50 files per upload'}, status=400)
        
        validation_time = time.time() - request_start_time
        logger.info(f"[UPLOAD] Validation complete in {validation_time:.2f}s")
        
        minio_start = time.time()
        minio_client = get_minio_client()
        bronze_bucket = 'genomic-bronze'
        logger.info(f"[UPLOAD] MinIO client initialized in {time.time() - minio_start:.2f}s")
        
        # Track created objects for rollback on error
        created_db_objects = []
        compressed_objects = []
        
        try:
            # Verify files exist in MinIO and compress if needed
            logger.info(f"[UPLOAD] Starting file verification and compression for {len(uploaded_files)} files")
            async with db_pool.acquire() as conn:
                bronze_objects = []
                
                for file_idx, file_info in enumerate(uploaded_files):
                    object_path = file_info['object_path']
                    filename = file_info['filename']
                    file_start = time.time()
                
                # Verify file exists in MinIO
                try:
                    stat_start = time.time()
                    stat = minio_client.client.stat_object(bronze_bucket, object_path)
                    stat_time = time.time() - stat_start
                    logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] Verified {filename} in MinIO: {stat.size / 1024 / 1024:.1f} MB (stat: {stat_time:.3f}s)")
                    
                    # Check if file needs compression
                    async_compression = False
                    if not filename.endswith('.gz'):
                        file_size_gb = stat.size / 1024 / 1024 / 1024
                        
                        # For large files (>5 GB), compress asynchronously
                        if file_size_gb > 5.0:
                            logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] File is {file_size_gb:.1f} GB - scheduling async compression")
                            
                            # Enqueue compression task
                            from tasks.compression_tasks import compress_file_async
                            compression_queue = get_pipeline_queue()
                            
                            compression_job = compression_queue.enqueue(
                                compress_file_async,
                                bucket_name=bronze_bucket,
                                object_path=object_path,
                                sample_code=sample_code,
                                filename=filename,
                                original_size=stat.size,
                                job_timeout='2h'
                            )
                            
                            logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] Compression job queued: {compression_job.id}")
                            logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] File will be compressed in background - storing uncompressed version temporarily")
                            async_compression = True
                            
                        if not async_compression:
                            # For smaller files (<5 GB), compress synchronously
                            compression_start = time.time()
                            logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] Starting synchronous compression for {filename} ({stat.size / 1024 / 1024:.1f} MB)...")
                            
                            # OPTIMIZED: Stream compression without loading full file into RAM
                            import tempfile
                            import subprocess
                            import multiprocessing
                            
                            # Create temp files for streaming
                            tmp_in = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.fastq')
                            tmp_out = tempfile.NamedTemporaryFile(mode='rb', delete=False, suffix='.fastq.gz')
                            tmp_in_path = tmp_in.name
                            tmp_out_path = tmp_out.name
                            
                            try:
                                # OPTIMIZATION #1: Stream download in chunks (не загружаем весь файл в RAM)
                                download_start = time.time()
                                logger.info(f"[UPLOAD] [{file_idx}/{len(uploaded_files)}] Starting download from MinIO (streaming)...")
                                response = minio_client.client.get_object(bronze_bucket, object_path)
                                
                                chunk_size = 64 * 1024 * 1024  # 64 MB chunks
                                total_downloaded = 0
                                chunk_count = 0
                                last_log_time = time.time()
                                
                                for chunk in response.stream(chunk_size):
                                    tmp_in.write(chunk)
                                    total_downloaded += len(chunk)
                                    chunk_count += 1
                                    
                                    # Log every 5 seconds or every 5 chunks
                                    if time.time() - last_log_time > 5 or chunk_count % 5 == 0:
                                        progress_pct = (total_downloaded / stat.size * 100) if stat.size > 0 else 0
                                        speed_mbps = (total_downloaded / (time.time() - download_start)) / 1024 / 1024
                                        logger.info(f"[UPLOAD] [{file_idx}/{len(uploaded_files)}] Download progress: {progress_pct:.1f}% ({total_downloaded / 1024 / 1024:.1f} MB) @ {speed_mbps:.1f} MB/s")
                                        last_log_time = time.time()
                                
                                tmp_in.close()
                                response.close()
                                response.release_conn()
                                
                                original_size = total_downloaded
                                download_time = time.time() - download_start
                                download_speed = original_size / download_time / 1024 / 1024
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Download: {original_size / 1024 / 1024:.1f} MB in {download_time:.1f}s ({download_speed:.1f} MB/s)")
                            
                                # OPTIMIZATION #2: Use pigz with output file (не загружаем output в RAM)
                                compress_start = time.time()
                                max_threads = multiprocessing.cpu_count()
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Compressing with pigz -p {max_threads}...")
                                
                                result = subprocess.run(
                                    ['pigz', '-p', str(max_threads), '-6', '-c', tmp_in_path],
                                    stdout=open(tmp_out_path, 'wb'),
                                    stderr=subprocess.PIPE,
                                    check=True
                                )
                                
                                compress_time = time.time() - compress_start
                                compressed_size = os.path.getsize(tmp_out_path)
                                compression_ratio = (1 - compressed_size / original_size) * 100
                                compress_speed = original_size / compress_time / 1024 / 1024
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Compress: {original_size / 1024 / 1024:.1f} MB → {compressed_size / 1024 / 1024:.1f} MB in {compress_time:.1f}s ({compress_speed:.1f} MB/s, {compression_ratio:.1f}% reduction)")
                            
                                # OPTIMIZATION #3: Stream upload from file (не загружаем в RAM)
                                upload_start = time.time()
                                compressed_filename = filename + '.gz'
                                compressed_path = f"{sample_code}/raw/{compressed_filename}"
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Uploading compressed to MinIO: {compressed_size / 1024 / 1024:.1f} MB...")
                                
                                with open(tmp_out_path, 'rb') as compressed_file:
                                    minio_client.client.put_object(
                                        bronze_bucket,
                                        compressed_path,
                                        compressed_file,
                                        compressed_size,
                                        content_type='application/gzip'
                                    )
                                
                                upload_time = time.time() - upload_start
                                upload_speed = compressed_size / upload_time / 1024 / 1024
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Upload: {compressed_size / 1024 / 1024:.1f} MB in {upload_time:.1f}s ({upload_speed:.1f} MB/s)")
                                
                                # Delete uncompressed file
                                delete_start = time.time()
                                minio_client.client.remove_object(bronze_bucket, object_path)
                                delete_time = time.time() - delete_start
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}]   Deleted original (took {delete_time:.3f}s)")
                                
                                # Use compressed file info
                                object_path = compressed_path
                                filename = compressed_filename
                                stat = minio_client.client.stat_object(bronze_bucket, compressed_path)
                                
                                total_file_time = time.time() - compression_start
                                logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] ✓ Compression complete: {total_file_time:.1f}s total (download: {download_time:.1f}s, compress: {compress_time:.1f}s, upload: {upload_time:.1f}s, delete: {delete_time:.3f}s)")
                            
                            except subprocess.CalledProcessError as e:
                                logger.error(f"pigz compression failed: {e.stderr.decode()}")
                                # Fallback: load file and use gzip (slower but works)
                                logger.warning("Falling back to in-memory gzip compression...")
                                with open(tmp_in_path, 'rb') as f:
                                    import gzip
                                    uncompressed_data = f.read()
                                    compressed_data = gzip.compress(uncompressed_data, compresslevel=6)
                                
                                compressed_filename = filename + '.gz'
                                compressed_path = f"{sample_code}/raw/{compressed_filename}"
                                
                                from io import BytesIO
                                minio_client.client.put_object(
                                    bronze_bucket,
                                    compressed_path,
                                    BytesIO(compressed_data),
                                    len(compressed_data),
                                    content_type='application/gzip'
                                )
                                
                                minio_client.client.remove_object(bronze_bucket, object_path)
                                object_path = compressed_path
                                filename = compressed_filename
                                stat = minio_client.client.stat_object(bronze_bucket, compressed_path)
                                
                            finally:
                                # Cleanup temp files
                                for tmp_path in [tmp_in_path, tmp_out_path]:
                                    if os.path.exists(tmp_path):
                                        os.unlink(tmp_path)
                    
                    # Create minio_objects record
                    db_start = time.time()
                    
                    # Get bucket_id for genomic-bronze
                    bucket_id = await conn.fetchval(
                        "SELECT bucket_id FROM minio_buckets WHERE bucket_name = $1",
                        bronze_bucket
                    )
                    if not bucket_id:
                        # Create bucket if not exists
                        bucket_id = await conn.fetchval(
                            "INSERT INTO minio_buckets (bucket_name) VALUES ($1) RETURNING bucket_id",
                            bronze_bucket
                        )
                    
                    query = """
                        INSERT INTO minio_objects 
                        (bucket_id, object_key, object_name, object_size_bytes, 
                         content_type, etag, sample_id, layer_stage)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING object_id
                    """
                    object_id = await conn.fetchval(
                        query,
                        bucket_id,
                        object_path,
                        filename,
                        stat.size,
                        'application/gzip' if filename.endswith('.gz') else 'application/octet-stream',
                        stat.etag,
                        sample_id,
                        'bronze'
                    )
                    db_time = time.time() - db_start
                    
                    bronze_objects.append({
                        'object_id': object_id,
                        'filename': filename,
                        'minio_path': object_path,
                        'size': stat.size
                    })
                    
                    created_db_objects.append(object_id)
                    file_total_time = time.time() - file_start
                    logger.info(f"[UPLOAD] [{file_idx+1}/{len(uploaded_files)}] ✓ Registered in DB (took {db_time:.3f}s, file total: {file_total_time:.1f}s)")
                    
                except Exception as e:
                    logger.error(f"File verification failed for {object_path}: {e}")
                    # Rollback: delete created DB records
                    if created_db_objects:
                        await conn.execute(
                            "DELETE FROM minio_objects WHERE object_id = ANY($1)",
                            created_db_objects
                        )
                    return json({'error': f'File not found in MinIO: {object_path}'}, status=400)
                
                # Update pipeline paths
                bronze_path = f"genomic-bronze/{sample_code}/raw/"
                silver_path = f"genomic-silver/{sample_code}/"
                results_path = f"/results/{sample_code}"
                
                await conn.execute("""
                    UPDATE pipeline_runs
                    SET bronze_path = $1, silver_path = $2
                    WHERE pipeline_id = $3
                """, bronze_path, silver_path, pipeline_id)
                
                # Track progress
                await track_progress(
                    conn, pipeline_id, 'bronze_upload',
                    f'✓ Direct upload complete: {len(bronze_objects)} files',
                    'completed', 100,
                    {
                        'total_files': len(bronze_objects),
                        'total_size': sum(obj['size'] for obj in bronze_objects),
                        'bronze_path': bronze_path
                    }
                )
            
            # Enqueue pipeline
            enqueue_start = time.time()
            job = enqueue_pipeline(
                pipeline_id=pipeline_id,
                sample_code=sample_code,
                input_dir=bronze_path,
                output_dir=results_path,
                params=parameters
            )
            enqueue_time = time.time() - enqueue_start
            logger.info(f"[UPLOAD] Pipeline enqueued: job_id={job.id} (took {enqueue_time:.3f}s)")
            
            # Update pipeline with job_id
            db_update_start = time.time()
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE pipeline_runs SET job_id = $1 WHERE pipeline_id = $2",
                    job.id, pipeline_id
                )
            db_update_time = time.time() - db_update_start
            
            total_confirm_time = time.time() - confirm_start
            logger.info(f"[UPLOAD] ✓ Confirm-upload complete: {total_confirm_time:.1f}s total (files: {len(bronze_objects)}, enqueue: {enqueue_time:.3f}s, db_update: {db_update_time:.3f}s)")
            
            return json({
                'success': True,
                'pipeline_id': pipeline_id,
                'job_id': job.id,
                'sample_code': sample_code,
                'files_uploaded': len(bronze_objects),
                'message': f'Pipeline queued successfully with job {job.id}',
                'status': 'queued',
                'timing': {
                    'total_seconds': round(total_confirm_time, 1),
                    'enqueue_seconds': round(enqueue_time, 3),
                    'db_update_seconds': round(db_update_time, 3)
                }
            })
        
        except Exception as inner_e:
            # Rollback: delete created DB records
            logger.error(f"Error in confirm_upload inner block: {inner_e}", exc_info=True)
            if created_db_objects:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM bronze_objects WHERE object_id = ANY($1)",
                        created_db_objects
                    )
                    logger.info(f"Rolled back {len(created_db_objects)} minio_objects records")
            raise
        
    except Exception as e:
        logger.error(f"Error confirming upload: {str(e)}", exc_info=True)
        return json({'error': 'Failed to confirm upload. Check server logs for details.'}, status=500)


@pipeline_bp.post("/submit")
@protected
async def submit_pipeline(request):
    """
    Submit a new genomic pipeline run (LEGACY - use presigned upload instead)
    
    🔒 PROTECTED ENDPOINT - Requires authentication
    
    ⚠️  DEPRECATED: This endpoint loads entire files into memory and is inefficient.
    Use /presigned-upload + /confirm-upload flow instead for better performance.
    This endpoint will be removed in future versions.
    
    ⚠️  SECURITY WARNING: No file size limits enforced - can cause OOM.
    
    Headers:
        Authorization: Bearer <token>
    
    Expects multipart/form-data with:
    - files: FASTQ files
    - sample_code: str (unique identifier)
    - sample_type: str (nanopore|illumina|pacbio)
    - collection_date: date (ISO format)
    - pipeline_name: str (e.g., 'nextflow_pipeline')
    - parameters: JSON string with pipeline parameters
    - notes: str (optional)
    """
    try:
        # Get authenticated user
        user_id = request.ctx.user['user_id']
        logger.info(f"Pipeline submission by user {request.ctx.user['username']} (ID: {user_id})")
        
        db_pool = await get_db_pool(request.app)
        
        # Get form data
        sample_code = request.form.get('sample_code')
        sample_type = request.form.get('sample_type', 'nanopore')
        collection_date_str = request.form.get('collection_date', datetime.now().date().isoformat())
        pipeline_name = request.form.get('pipeline_name', 'nextflow_pipeline')
        parameters = json_lib.loads(request.form.get('parameters', '{}'))
        notes = request.form.get('notes', '')
        
        # Parse collection date
        try:
            collection_date = datetime.fromisoformat(collection_date_str).date()
        except Exception:
            collection_date = date.today()
        
        # Get uploaded files
        files = request.files.getlist('files')

        if not sample_code:
            return json({'error': 'sample_code is required'}, status=400)

        if not files:
            return json({'error': 'At least one FASTQ file is required'}, status=400)

        # Validate FASTQ files before processing
        logger.info(f"Validating {len(files)} FASTQ file(s) for sample {sample_code}")
        validation_result = validate_fastq_files(files)

        if not validation_result['valid']:
            error_details = '\n'.join(validation_result['errors'])
            logger.error(f"FASTQ validation failed for sample {sample_code}: {error_details}")
            return json({
                'error': 'FASTQ file validation failed',
                'details': validation_result['errors'],
                'warnings': validation_result['warnings']
            }, status=400)

        # Log validation success
        total_mb = validation_result['total_size'] / (1024**2)
        logger.info(f"FASTQ validation passed: {validation_result['files_validated']} files, {total_mb:.2f} MB total")
        if validation_result['warnings']:
            for warning in validation_result['warnings']:
                logger.info(f"  {warning}")

        # Initialize variables
        progress_steps = []
        uploaded_bronze_info = []
        
        # Initialize MinIO client
        minio_client = get_minio_client()
        
        # Define paths BEFORE database operations
        results_path = f"/results/{sample_code}"
        log_path = f"{results_path}/nextflow.log"
        trace_path = f"{results_path}/nextflow_trace.txt"
        report_path = f"{results_path}/nextflow_report.html"
        timeline_path = f"{results_path}/nextflow_timeline.html"
        work_dir = f"/tmp/nextflow/work/{sample_code}"
        
        Path(results_path).mkdir(parents=True, exist_ok=True)
        
        # Create database records and upload to Bronze
        async with db_pool.acquire() as conn:
            # Create sample
            sample_id = await create_sample_record(
                conn, sample_code, sample_type, collection_date, notes
            )
            
            # Create pipeline run record FIRST to get pipeline_id for progress tracking
            pipeline_id = await create_pipeline_run(
                conn, sample_id, pipeline_name, parameters, 
                results_path, log_path
            )
            
            # Start progress tracking
            await track_progress(
                conn, pipeline_id, 'bronze_upload', 
                'Initializing Bronze layer upload', 
                'started', 0,
                {'total_files': len(files)}
            )
            
            # Upload files directly to Bronze layer (permanent storage)
            import time
            for idx, uploaded_file in enumerate(files):
                file_start_time = time.time()
                file_progress = int((idx / len(files)) * 100)
                
                logger.info(f"Processing file {idx+1}/{len(files)}: {uploaded_file.name} ({len(uploaded_file.body)} bytes)")
                
                # Track compression step
                await track_progress(
                    conn, pipeline_id, 'bronze_upload',
                    f'Compressing {uploaded_file.name}',
                    'in_progress', file_progress,
                    {'filename': uploaded_file.name, 'original_size': len(uploaded_file.body)}
                )
                
                bronze_info = await upload_to_bronze(
                    conn, 
                    minio_client, 
                    sample_code, 
                    uploaded_file.body,
                    uploaded_file.name,
                    sample_id
                )
                uploaded_bronze_info.append(bronze_info)
                
                file_total_time = time.time() - file_start_time
                logger.info(f"✓ File {uploaded_file.name} processed in {file_total_time:.2f}s (compression + upload)")
                
                # Track upload completion
                await track_progress(
                    conn, pipeline_id, 'bronze_upload',
                    f'✓ Uploaded {bronze_info["filename"]} to Bronze',
                    'in_progress', file_progress + int(100/len(files)),
                    {
                        'filename': bronze_info['filename'],
                        'original_size': bronze_info['original_size'],
                        'final_size': bronze_info['final_size'],
                        'compression_ratio': bronze_info.get('compression_ratio', 1.0),
                        'minio_path': bronze_info['minio_path']
                    }
                )
                
                logger.info(f"✓ Uploaded to bronze: {bronze_info['minio_path']} ({bronze_info['final_size']} bytes)")
            
            # Bronze upload complete
            await track_progress(
                conn, pipeline_id, 'bronze_upload',
                f'✓ Bronze upload complete: {len(files)} files uploaded',
                'completed', 100,
                {
                    'total_files': len(files),
                    'total_size': sum(f['final_size'] for f in uploaded_bronze_info),
                    'bronze_path': f"genomic-bronze/{sample_code}/raw/"
                }
            )
            
            # Set lakehouse paths
            bronze_path = f"genomic-bronze/{sample_code}/raw/"
            silver_path = f"genomic-silver/{sample_code}/"
            
            # Update lakehouse paths
            await conn.execute("""
                UPDATE pipeline_runs 
                SET bronze_path = $1, silver_path = $2 
                WHERE pipeline_id = $3
            """, bronze_path, silver_path, pipeline_id)
            
            # Create Nextflow execution record
            await track_progress(
                conn, pipeline_id, 'nextflow_prep',
                'Creating Nextflow execution record',
                'in_progress', 10
            )
            
            execution_id = await create_nextflow_execution(
                conn, pipeline_id, sample_code, work_dir, results_path,
                trace_path, report_path, timeline_path, parameters
            )
            
            logger.info(f"Created pipeline run {pipeline_id} with Nextflow execution {execution_id} for sample {sample_code}")
        
        # Queue Nextflow pipeline with Redis Queue (RQ)
        progress_steps.append("Queuing pipeline execution with Redis Queue")

        # Enqueue pipeline execution
        job = enqueue_pipeline(
            pipeline_id=pipeline_id,
            sample_code=sample_code,
            input_dir=str(bronze_path),  # Will download from bronze
            output_dir=str(results_path),
            params=parameters
        )

        # Update pipeline with job_id
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE pipeline_runs SET job_id = $1 WHERE pipeline_id = $2",
                job.id, pipeline_id
            )

        logger.info(f"Pipeline {pipeline_id} enqueued with job ID: {job.id}")

        return json({
            'success': True,
            'pipeline_id': pipeline_id,
            'job_id': job.id,
            'sample_id': sample_id,
            'sample_code': sample_code,
            'files_uploaded': len(uploaded_bronze_info),
            'bronze_objects': len(uploaded_bronze_info),
            'progress_steps': progress_steps,
            'message': f'Pipeline {pipeline_id} queued successfully with job {job.id}',
            'status': 'queued',
            'fastq_files': [f['filename'] for f in uploaded_bronze_info],
            'bronze_path': bronze_path,
            'results_path': results_path,
            'queue_position': job.connection.llen('rq:queue:pipeline-queue')
        }, status=201)
        
    except Exception as e:
        logger.error(f"Pipeline submission error: {str(e)}", exc_info=True)
        return json({'error': f'Submission failed: {str(e)}'}, status=500)


# ==================== JOB MANAGEMENT (Redis Queue) ====================

@pipeline_bp.get("/job/<job_id:str>/status")
async def get_job_status_endpoint(request, job_id):
    """
    Get RQ job status

    Returns:
        Job status: queued, started, finished, failed
    """
    try:
        status = get_job_status(job_id)
        return json(status)
    except Exception as e:
        import traceback
        logger.error(f"Error fetching job status for {job_id}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return json({'error': str(e), 'job_id': job_id}, status=404)


@pipeline_bp.post("/job/<job_id:str>/cancel")
@protected
async def cancel_job_endpoint(request, job_id):
    """
    Cancel a queued or running job
    
    🔒 PROTECTED ENDPOINT - Requires authentication

    Headers:
        Authorization: Bearer <token>
        
    Returns:
        Success status
    """
    try:
        user_id = request.ctx.user['user_id']
        logger.info(f"Job cancellation requested by user {request.ctx.user['username']} (ID: {user_id}) for job {job_id}")
        
        db_pool = await get_db_pool(request.app)
        
        # Check current status before cancelling (prevent race condition)
        async with db_pool.acquire() as conn:
            current_status = await conn.fetchval(
                "SELECT status FROM pipeline_runs WHERE job_id = $1",
                job_id
            )
            
            if not current_status:
                return json({
                    'success': False,
                    'job_id': job_id,
                    'message': 'Pipeline not found'
                }, status=404)
            
            if current_status not in ('queued', 'running'):
                return json({
                    'success': False,
                    'job_id': job_id,
                    'message': f'Cannot cancel pipeline in status: {current_status}'
                }, status=400)
        
        success = cancel_job(job_id)

        if success:
            # Atomically update status only if still in cancellable state
            async with db_pool.acquire() as conn:
                rows_updated = await conn.fetchval("""
                    UPDATE pipeline_runs
                    SET status = 'cancelled', completed_at = CURRENT_TIMESTAMP
                    WHERE job_id = $1 AND status IN ('queued', 'running')
                    RETURNING pipeline_id
                """, job_id)
                
                if not rows_updated:
                    return json({
                        'success': False,
                        'job_id': job_id,
                        'message': 'Pipeline status changed before cancellation could complete'
                    }, status=409)

            return json({
                'success': True,
                'job_id': job_id,
                'message': f'Job {job_id} cancelled successfully'
            })
        else:
            return json({
                'success': False,
                'job_id': job_id,
                'message': 'Job could not be cancelled (may already be completed)'
            }, status=400)

    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return json({'error': str(e), 'job_id': job_id}, status=500)


# ==================== PROGRESS TRACKING ====================

@pipeline_bp.get("/runs/<pipeline_id:int>/progress")
async def get_pipeline_progress(request, pipeline_id):
    """
    Get real-time progress events for a pipeline run

    Returns:
        List of progress events with stages, steps, and percentages
    """
    try:
        db_pool = await get_db_pool(request.app)

        async with db_pool.acquire() as conn:
            events = await fetch_pipeline_progress_events(conn, pipeline_id)
        
        return json({
            'pipeline_id': pipeline_id,
            'events': events,
            'total_events': len(events)
        })
        
    except Exception as e:
        logger.error(f"Error fetching pipeline progress: {e}", exc_info=True)
        return json({'error': str(e)}, status=500)


# ==================== PIPELINE LISTING ====================

@pipeline_bp.get("/runs")
async def get_pipeline_runs(request):
    """
    Get list of pipeline runs with optional filtering
    
    Query parameters:
    - status: filter by status (queued|running|completed|failed|cancelled)
    - limit: number of results (default all)
    - offset: pagination offset
    - sample_code: filter by sample code
    - date_from: filter runs created after (ISO format)
    - date_to: filter runs created before (ISO format)
    - min_runtime: minimum runtime in minutes
    - max_runtime: maximum runtime in minutes
    """
    try:
        db_pool = await get_db_pool(request.app)
        
        # Parse query parameters
        status_filter = request.args.get('status')
        
        # Validate and limit pagination parameters to prevent DoS
        try:
            limit = min(int(request.args.get('limit', 10000)), 10000) if request.args.get('limit') else 10000  # Default all (max 10000)
            offset = max(int(request.args.get('offset', 0)), 0)  # No negative offsets
        except (ValueError, TypeError):
            return json({'error': 'Invalid limit or offset parameter'}, status=400)
        
        sample_code = request.args.get('sample_code')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        min_runtime = request.args.get('min_runtime')
        max_runtime = request.args.get('max_runtime')
        
        # Convert date strings to datetime objects
        from datetime import datetime
        if date_from:
            try:
                date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return json({'error': 'Invalid date_from format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)'}, status=400)
        
        if date_to:
            try:
                date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return json({'error': 'Invalid date_to format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)'}, status=400)
        
        # Build query
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
                s.sample_id,
                COALESCE(s.sample_code, pr.sample_name) as sample_code,
                COALESCE(s.sample_type, pr.sample_type) as sample_type,
                s.collection_date,
                s.sequencing_platform,
                l.location_name,
                l.country,
                l.city,
                pr.location,
                pr.sample_name
            FROM pipeline_runs pr
            LEFT JOIN samples s ON pr.sample_id = s.sample_id
            LEFT JOIN locations l ON s.location_id = l.location_id
        """
        
        where_clauses = []
        params = []
        param_count = 1
        
        if status_filter:
            where_clauses.append(f"pr.status = ${param_count}")
            params.append(status_filter)
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
        
        if min_runtime:
            where_clauses.append(f"pr.runtime_minutes >= ${param_count}")
            params.append(float(min_runtime))
            param_count += 1
        
        if max_runtime:
            where_clauses.append(f"pr.runtime_minutes <= ${param_count}")
            params.append(float(max_runtime))
            param_count += 1
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += f" ORDER BY pr.created_at DESC LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([limit, offset])
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        # Parse metrics filters
        min_quality = request.args.get('min_quality')
        max_quality = request.args.get('max_quality')
        min_mags = request.args.get('min_mags')
        max_mags = request.args.get('max_mags')
        min_amr_risk = request.args.get('min_amr_risk')
        max_amr_risk = request.args.get('max_amr_risk')
        has_pathogens = request.args.get('has_pathogens')  # 'true' or 'false'
        
        # Helper function to load summary metrics from JSON
        def load_summary_metrics(results_path):
            """Load metrics from summary JSON file"""
            if not results_path or not os.path.exists(results_path):
                return None
            
            # Try to find summary JSON
            summary_dir = Path(results_path) / '00_summary'
            if summary_dir.exists():
                summary_files = list(summary_dir.glob('*_summary.json'))
                if summary_files:
                    try:
                        with open(summary_files[0], 'r') as f:
                            data = json_lib.load(f)
                            mags = data.get('mags', {})
                            return {
                                'quality_score': data.get('quality_score'),
                                'amr_risk_score': data.get('amr_risk_score'),
                                'total_mags': mags.get('total_bins', 0) if mags else 0,
                                'high_quality_mags': mags.get('high_quality', 0) if mags else 0,
                                'pathogens_count': len(data.get('pathogens', []))
                            }
                    except Exception:
                        pass
            return None
        
        runs = []
        for row in rows:
            # Load summary metrics
            metrics = load_summary_metrics(row['results_path'])
            
            # Apply metrics filters
            if metrics:
                # Quality Score filter
                if min_quality and (metrics['quality_score'] is None or metrics['quality_score'] < float(min_quality)):
                    continue
                if max_quality and (metrics['quality_score'] is None or metrics['quality_score'] > float(max_quality)):
                    continue
                
                # MAGs filter
                if min_mags and metrics['total_mags'] < int(min_mags):
                    continue
                if max_mags and metrics['total_mags'] > int(max_mags):
                    continue
                
                # AMR Risk filter
                if min_amr_risk and (metrics['amr_risk_score'] is None or metrics['amr_risk_score'] < float(min_amr_risk)):
                    continue
                if max_amr_risk and (metrics['amr_risk_score'] is None or metrics['amr_risk_score'] > float(max_amr_risk)):
                    continue
                
                # Pathogens filter
                if has_pathogens == 'true' and metrics['pathogens_count'] == 0:
                    continue
                if has_pathogens == 'false' and metrics['pathogens_count'] > 0:
                    continue
            elif any([min_quality, max_quality, min_mags, max_mags, min_amr_risk, max_amr_risk, has_pathogens]):
                # If filters are set but no metrics available, skip this run
                continue
            
            # Use location from pipeline_runs if locations table has no data
            location_data = None
            if row['location_name']:
                location_data = {
                    'name': row['location_name'],
                    'city': row['city'],
                    'country': row['country']
                }
            elif row['location']:
                location_data = {'name': row['location']}
            
            run_data = {
                'id': row['pipeline_id'],
                'pipeline_name': row['pipeline_name'],
                'pipeline_version': row['pipeline_version'],
                'status': row['status'],
                'sample_id': row['sample_id'],
                'sample_code': row['sample_code'],
                'sample_type': row['sample_type'],
                'collection_date': row['collection_date'].isoformat() if row['collection_date'] else None,
                'sequencing_platform': row['sequencing_platform'],
                'location': location_data,
                'parameters': row['parameters'],
                'results_path': row['results_path'],
                'log_file_path': row['log_file_path'],
                'exit_code': row['exit_code'],
                'error_message': row['error_message'],
                'runtime_minutes': row['runtime_minutes'],
                'queued_at': row['queued_at'].isoformat() if row['queued_at'] else None,
                'started_at': row['started_at'].isoformat() if row['started_at'] else None,
                'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None
            }
            
            # Add metrics if available
            if metrics:
                run_data['metrics'] = metrics
            
            runs.append(run_data)
        
        return json({
            'runs': runs,
            'count': len(runs),
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error fetching pipeline runs: {str(e)}", exc_info=True)
        return json({'error': f'Failed to fetch runs: {str(e)}'}, status=500)


# ==================== PIPELINE DETAILS ====================

@pipeline_bp.get("/runs/<pipeline_id:int>")
async def get_pipeline_run(request, pipeline_id):
    """Get detailed information about a specific pipeline run"""
    try:
        db_pool = await get_db_pool(request.app)
        
        query = """
            SELECT 
                pr.*,
                s.sample_code,
                s.sample_type,
                s.collection_date,
                s.sequencing_platform,
                s.notes,
                l.location_name,
                l.country,
                l.city,
                l.latitude,
                l.longitude
            FROM pipeline_runs pr
            JOIN samples s ON pr.sample_id = s.sample_id
            LEFT JOIN locations l ON s.location_id = l.location_id
            WHERE pr.pipeline_id = $1
        """
        
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, pipeline_id)
        
        if not row:
            raise NotFound(f"Pipeline run {pipeline_id} not found")
        
        # Get result files if completed
        result_files = []
        if row['results_path'] and Path(row['results_path']).exists():
            results_dir = Path(row['results_path'])
            result_files = [
                {
                    'name': f.name,
                    'path': str(f.relative_to(results_dir)),
                    'size': f.stat().st_size,
                    'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                }
                for f in results_dir.rglob('*') if f.is_file()
            ]
        
        run_data = {
            'id': row['pipeline_id'],
            'pipeline_name': row['pipeline_name'],
            'pipeline_version': row['pipeline_version'],
            'status': row['status'],
            'sample': {
                'id': row['sample_id'],
                'code': row['sample_code'],
                'type': row['sample_type'],
                'collection_date': row['collection_date'].isoformat() if row['collection_date'] else None,
                'platform': row['sequencing_platform'],
                'notes': row['notes']
            },
            'location': {
                'name': row['location_name'],
                'city': row['city'],
                'country': row['country'],
                'latitude': float(row['latitude']) if row['latitude'] else None,
                'longitude': float(row['longitude']) if row['longitude'] else None
            } if row['location_name'] else None,
            'parameters': row['parameters'],
            'results_path': row['results_path'],
            'log_file_path': row['log_file_path'],
            'exit_code': row['exit_code'],
            'error_message': row['error_message'],
            'runtime_minutes': row['runtime_minutes'],
            'cpu_cores': row['cpu_cores'],
            'memory_gb': row['memory_gb'],
            'queued_at': row['queued_at'].isoformat() if row['queued_at'] else None,
            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'result_files': result_files
        }
        
        return json(run_data)
        
    except NotFound as e:
        return json({'error': str(e)}, status=404)
    except Exception as e:
        logger.error(f"Error fetching pipeline run {pipeline_id}: {str(e)}", exc_info=True)
        return json({'error': f'Failed to fetch run: {str(e)}'}, status=500)


# ==================== PIPELINE LOGS ====================

@pipeline_bp.get("/runs/<pipeline_id:int>/log")
async def get_pipeline_log(request, pipeline_id):
    """Get execution log for a pipeline run"""
    try:
        db_pool = await get_db_pool(request.app)
        
        # Validate lines parameter
        try:
            lines = min(int(request.args.get('lines', 100)), 10000)  # Max 10k lines
            if lines < 1:
                lines = 100
        except (ValueError, TypeError):
            return json({'error': 'Invalid lines parameter'}, status=400)
        
        # Get log file path from database
        query = "SELECT log_file_path FROM pipeline_runs WHERE pipeline_id = $1"
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, pipeline_id)
        
        if not row:
            raise NotFound(f"Pipeline run {pipeline_id} not found")
        
        log_path = row['log_file_path']
        if not log_path or not Path(log_path).exists():
            return json({
                'pipeline_id': pipeline_id,
                'log': 'Log file not available yet',
                'lines': 0
            })
        
        # Read last N lines
        try:
            result = subprocess.run(
                ['tail', '-n', str(lines), log_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            log_content = result.stdout
        except Exception as e:
            log_content = f"Error reading log: {str(e)}"
        
        return json({
            'pipeline_id': pipeline_id,
            'log': log_content,
            'lines': len(log_content.splitlines()),
            'log_path': log_path
        })
        
    except NotFound as e:
        return json({'error': str(e)}, status=404)
    except Exception as e:
        logger.error(f"Error reading log for pipeline {pipeline_id}: {str(e)}", exc_info=True)
        return json({'error': f'Failed to read log: {str(e)}'}, status=500)


# ==================== PIPELINE PROCESSES ====================

@pipeline_bp.get("/runs/<pipeline_id:int>/processes")
async def get_pipeline_processes(request, pipeline_id):
    """
    Get detailed list of all Nextflow processes for a pipeline run
    
    Returns:
    - List of all processes (NanoPlot, Filtlong, Flye, MetaBAT2, CONCOCT, CheckM)
    - Each with status, timing, resource usage, and intermediate results
    """
    try:
        db_pool = await get_db_pool(request.app)
        
        # Get execution_id for this pipeline
        async with db_pool.acquire() as conn:
            execution_id = await conn.fetchval(
                "SELECT nextflow_execution_id FROM pipeline_runs WHERE pipeline_id = $1",
                pipeline_id
            )
            
            if not execution_id:
                return json({
                    'pipeline_id': pipeline_id,
                    'processes': [],
                    'message': 'No Nextflow execution found for this pipeline run'
                })
            
            # Get all processes for this execution
            query = """
                SELECT 
                    process_id,
                    process_name,
                    task_id,
                    status,
                    exit_code,
                    start_time,
                    complete_time,
                    EXTRACT(EPOCH FROM duration) as duration_seconds,
                    cpu_usage,
                    peak_memory_mb,
                    peak_vmem_mb,
                    disk_read_mb,
                    disk_write_mb,
                    container_image,
                    work_directory,
                    attempt,
                    error_action,
                    input_files,
                    output_files
                FROM nextflow_processes
                WHERE execution_id = $1
                ORDER BY start_time ASC
            """
            
            rows = await conn.fetch(query, execution_id)
        
        processes = []
        for row in rows:
            processes.append({
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
                'vmem_mb': float(row['peak_vmem_mb']) if row['peak_vmem_mb'] else None,
                'disk_read_mb': float(row['disk_read_mb']) if row['disk_read_mb'] else None,
                'disk_write_mb': float(row['disk_write_mb']) if row['disk_write_mb'] else None,
                'container': row['container_image'],
                'work_dir': row['work_directory'],
                'attempt': row['attempt'],
                'error_action': row['error_action'],
                'input_files': row['input_files'],
                'output_files': row['output_files']
            })
        
        return json({
            'pipeline_id': pipeline_id,
            'execution_id': execution_id,
            'total_processes': len(processes),
            'processes': processes
        })
        
    except Exception as e:
        logger.error(f"Error fetching processes for pipeline {pipeline_id}: {str(e)}", exc_info=True)
        return json({'error': f'Failed to fetch processes: {str(e)}'}, status=500)


@pipeline_bp.get("/runs/<pipeline_id:int>/timeline")
async def get_pipeline_timeline(request, pipeline_id):
    """Get Nextflow timeline HTML report"""
    try:
        db_pool = await get_db_pool(request.app)
        
        # Get timeline file path from execution record
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT ne.timeline_file_path 
                FROM pipeline_runs pr
                JOIN nextflow_executions ne ON pr.nextflow_execution_id = ne.execution_id
                WHERE pr.pipeline_id = $1
            """, pipeline_id)
        
        if not row or not row['timeline_file_path']:
            raise NotFound(f"Timeline not found for pipeline {pipeline_id}")
        
        timeline_path = Path(row['timeline_file_path'])
        if not timeline_path.exists():
            raise NotFound(f"Timeline file does not exist: {timeline_path}")
        
        # Return HTML file
        return await file_response(str(timeline_path), mime_type='text/html')
        
    except NotFound as e:
        return json({'error': str(e)}, status=404)
    except Exception as e:
        logger.error(f"Error serving timeline: {str(e)}", exc_info=True)
        return json({'error': f'Failed to serve timeline: {str(e)}'}, status=500)


@pipeline_bp.get("/runs/<pipeline_id:int>/report")
async def get_pipeline_report(request, pipeline_id):
    """Get Nextflow execution report HTML"""
    try:
        db_pool = await get_db_pool(request.app)
        
        # Get report file path from execution record
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT ne.report_file_path 
                FROM pipeline_runs pr
                JOIN nextflow_executions ne ON pr.nextflow_execution_id = ne.execution_id
                WHERE pr.pipeline_id = $1
            """, pipeline_id)
        
        if not row or not row['report_file_path']:
            raise NotFound(f"Report not found for pipeline {pipeline_id}")
        
        report_path = Path(row['report_file_path'])
        if not report_path.exists():
            raise NotFound(f"Report file does not exist: {report_path}")
        
        # Return HTML file
        return await file_response(str(report_path), mime_type='text/html')
        
    except NotFound as e:
        return json({'error': str(e)}, status=404)
    except Exception as e:
        logger.error(f"Error serving report: {str(e)}", exc_info=True)
        return json({'error': f'Failed to serve report: {str(e)}'}, status=500)


# ==================== PIPELINE STATISTICS ====================

@pipeline_bp.post("/cleanup-stuck")
@protected
async def cleanup_stuck_pipelines(request):
    """
    Clean up pipelines stuck in queued/running status for too long
    
    🔒 PROTECTED ENDPOINT - Requires authentication
    
    Query params:
    - hours: timeout threshold in hours (default: 2)
    - dry_run: if true, only return count without updating (default: false)
    """
    try:
        # Get authenticated user
        user_id = request.ctx.user['user_id']
        logger.info(f"Cleanup-stuck called by user {request.ctx.user['username']} (ID: {user_id})")
        db_pool = await get_db_pool(request.app)
        
        # Validate hours parameter
        try:
            hours = int(request.args.get('hours', 2))
            if hours < 1 or hours > 168:  # 1 hour to 1 week
                return json({'error': 'hours must be between 1 and 168'}, status=400)
        except (ValueError, TypeError):
            return json({'error': 'Invalid hours parameter'}, status=400)
        
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        
        async with db_pool.acquire() as conn:
            # Find stuck pipelines - use parameterized query to prevent SQL injection
            query = """
                SELECT pipeline_id, status, job_id, queued_at,
                       EXTRACT(EPOCH FROM (NOW() - queued_at))/3600 as hours_stuck
                FROM pipeline_runs
                WHERE status IN ('queued', 'running')
                  AND queued_at < NOW() - INTERVAL '1 hour' * $1
                ORDER BY queued_at
            """
            
            stuck_pipelines = await conn.fetch(query, hours)
            
            if dry_run:
                return json({
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
                })
            
            # Update stuck pipelines
            updated_count = 0
            for row in stuck_pipelines:
                hours_msg = f"{float(row['hours_stuck']):.1f}"
                await conn.execute("""
                    UPDATE pipeline_runs
                    SET status = 'timeout_failed',
                        error_message = $2,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE pipeline_id = $1
                """, row['pipeline_id'], f'Pipeline timed out after {hours_msg} hours')
                
                # Try to cancel job in Redis if exists
                if row['job_id']:
                    try:
                        cancel_job(row['job_id'])
                    except Exception as e:
                        logger.warning(f"Could not cancel job {row['job_id']}: {e}")
                
                updated_count += 1
                logger.info(f"Marked pipeline {row['pipeline_id']} as timeout_failed (stuck for {row['hours_stuck']:.1f}h)")
            
            return json({
                'success': True,
                'cleaned_up': updated_count,
                'threshold_hours': hours,
                'message': f'Cleaned up {updated_count} stuck pipelines'
            })
    
    except Exception as e:
        logger.error(f"Error cleaning up stuck pipelines: {e}", exc_info=True)
        return json({'error': str(e)}, status=500)


@pipeline_bp.get("/stats")
async def get_pipeline_stats(request):
    """Get pipeline execution statistics"""
    try:
        db_pool = await get_db_pool(request.app)
        
        query = """
            SELECT 
                COUNT(*) as total_runs,
                COUNT(*) FILTER (WHERE pr.status = 'completed') as completed,
                COUNT(*) FILTER (WHERE pr.status = 'failed') as failed,
                COUNT(*) FILTER (WHERE pr.status = 'running') as running,
                COUNT(*) FILTER (WHERE pr.status = 'queued') as pending,
                COUNT(*) FILTER (WHERE pr.created_at >= NOW() - INTERVAL '24 hours') as last_24h,
                COUNT(*) FILTER (WHERE pr.created_at >= NOW() - INTERVAL '7 days') as last_7d,
                AVG(pr.runtime_minutes) FILTER (WHERE pr.status = 'completed') as avg_runtime_minutes
            FROM pipeline_runs pr
            JOIN samples s ON pr.sample_id = s.sample_id
        """
        
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query)
        
        # Count by sample type
        type_query = """
            SELECT s.sample_type, COUNT(*) as count
            FROM pipeline_runs pr
            JOIN samples s ON pr.sample_id = s.sample_id
            GROUP BY s.sample_type
        """
        async with db_pool.acquire() as conn:
            type_rows = await conn.fetch(type_query)
        
        stats = {
            'total_runs': row['total_runs'],
            'completed': row['completed'],
            'failed': row['failed'],
            'running': row['running'],
            'pending': row['pending'],
            'last_24h': row['last_24h'],
            'last_7d': row['last_7d'],
            'avg_runtime_minutes': float(row['avg_runtime_minutes']) if row['avg_runtime_minutes'] else 0,
            'sample_types': [{'type': r['sample_type'], 'count': r['count']} for r in type_rows]
        }
        
        return json(stats)
        
    except Exception as e:
        logger.error(f"Error getting pipeline stats: {str(e)}", exc_info=True)
        return json({'error': f'Failed to get stats: {str(e)}'}, status=500)


# ==================== BACKGROUND TASKS ====================

async def upload_fastq_files_to_minio(app, sample_id, bucket_id, sample_code, files_info):
    """Upload FASTQ files to MinIO in background after returning HTTP response"""
    try:
        db_pool = await get_db_pool(app)
        minio_client = get_minio_client()
        
        logger.info(f"Starting background upload of {len(files_info)} files to MinIO for sample {sample_code}")
        
        for file_info in files_info:
            try:
                # Read file from disk and upload to MinIO
                with open(file_info['path'], 'rb') as f:
                    file_content = f.read()
                
                object_name = f"{sample_code}/{file_info['name']}"
                object_info = minio_client.upload_from_bytes(
                    MINIO_BUCKET,
                    object_name,
                    file_content,
                    content_type='application/octet-stream'
                )
                object_info['object_name'] = file_info['name']
                
                # Save to database
                async with db_pool.acquire() as conn:
                    await save_minio_object_to_db(conn, bucket_id, sample_id, object_info)
                
                logger.info(f"Uploaded {file_info['name']} to MinIO: {object_name}")
            except Exception as e:
                logger.error(f"MinIO upload failed for {file_info['name']}: {e}")
        
        logger.info(f"Completed background MinIO upload for sample {sample_code}")
    except Exception as e:
        logger.error(f"Background MinIO upload error for sample {sample_code}: {e}", exc_info=True)


# ==================== NEXTFLOW EXECUTION ====================

async def execute_nextflow_pipeline(app, pipeline_id, execution_id, sample_code, fastq_paths, 
                                   results_path, log_path, trace_path, parameters):
    """
    Execute Nextflow pipeline in background with full tracking
    Synchronized with Streamlit NextflowRunner logic
    """
    db_pool = await get_db_pool(app)
    
    try:
        # Update status to running
        async with db_pool.acquire() as conn:
            await update_pipeline_status(conn, pipeline_id, 'running')
            await update_nextflow_execution_status(conn, execution_id, 'running')
            
            # Track Nextflow preparation start
            await track_progress(
                conn, pipeline_id, 'nextflow_prep',
                'Preparing Nextflow environment',
                'in_progress', 20
            )
        
        logger.info(f"Starting Nextflow pipeline for sample {sample_code}")
        
        # Create work directory for Nextflow (needs write access for .nextflow/)
        work_dir_path = Path(f"/tmp/nextflow/work/{sample_code}")
        work_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Download files from Bronze layer to temp input directory
        input_dir = work_dir_path / "input"
        input_dir.mkdir(exist_ok=True)
        
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'bronze_download',
                f'Downloading from Bronze layer: genomic-bronze/{sample_code}/raw/',
                'in_progress', 0
            )
        
        logger.info(f"Downloading files from Bronze layer for sample {sample_code}")
        minio_client = get_minio_client()
        
        try:
            downloaded_files = await download_from_bronze(minio_client, sample_code, str(input_dir))
            logger.info(f"✓ Downloaded {len(downloaded_files)} files from bronze to {input_dir}")
            
            # Track download completion
            async with db_pool.acquire() as conn:
                total_size = sum(os.path.getsize(f) for f in downloaded_files if os.path.exists(f))
                await track_progress(
                    conn, pipeline_id, 'bronze_download',
                    f'✓ Downloaded {len(downloaded_files)} files from Bronze',
                    'completed', 100,
                    {
                        'file_count': len(downloaded_files),
                        'total_size': total_size,
                        'files': [os.path.basename(f) for f in downloaded_files]
                    }
                )
            
            # DEBUG: Verify files exist before Nextflow
            actual_files = os.listdir(str(input_dir))
            logger.info(f"DEBUG: Files in {input_dir}: {actual_files}")
            for f in downloaded_files:
                exists = os.path.exists(f)
                size = os.path.getsize(f) if exists else 0
                logger.info(f"DEBUG: {f} exists={exists}, size={size}")
                
        except Exception as e:
            error_msg = f"Failed to download from bronze: {str(e)}"
            logger.error(error_msg)
            async with db_pool.acquire() as conn:
                await update_pipeline_status(conn, pipeline_id, 'failed', error_msg, 1)
                await update_nextflow_execution_status(conn, execution_id, 'failed', 1, error_msg)
                await track_progress(
                    conn, pipeline_id, 'bronze_download',
                    f'Failed to download from Bronze: {error_msg}',
                    'failed', 0
                )
            return
        
        # Build Nextflow command
        nextflow_cmd = [
            'nextflow', 'run',
            '/nextflow/main.nf',
            '-profile', 'docker',
            '--input_dir', str(input_dir),  # Use temp input dir with bronze files
            '--outdir', results_path,
        ]
        
        # Add custom parameters
        for key, value in parameters.items():
            nextflow_cmd.extend([f'--{key}', str(value)])
        
        logger.info(f"Executing command: {' '.join(nextflow_cmd)}")
        
        # Track Nextflow execution start
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'nextflow_exec',
                'Starting Nextflow pipeline execution',
                'in_progress', 0,
                {'command': ' '.join(nextflow_cmd[:5]) + '...'}
            )
        
        # Execute Nextflow from work directory (needs write access)
        with open(log_path, 'w') as log_file:
            process = await asyncio.create_subprocess_exec(
                *nextflow_cmd,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(work_dir_path)  # Run from writable directory!
            )
            
            exit_code = await process.wait()
        
        # Parse trace file and create process records
        async with db_pool.acquire() as conn:
            processes_count = await parse_nextflow_trace(trace_path, execution_id, conn)
            logger.info(f"Parsed {processes_count} processes from trace file")
            
            # Track Nextflow completion
            if exit_code == 0:
                await track_progress(
                    conn, pipeline_id, 'nextflow_exec',
                    f'✓ Nextflow completed: {processes_count} processes executed',
                    'completed', 100,
                    {'processes_count': processes_count, 'exit_code': exit_code}
                )
            else:
                await track_progress(
                    conn, pipeline_id, 'nextflow_exec',
                    f'Nextflow failed with exit code {exit_code}',
                    'failed', 0,
                    {'exit_code': exit_code}
                )
        
        # Update status based on exit code
        status = 'completed' if exit_code == 0 else 'failed'
        error_msg = None if exit_code == 0 else f"Pipeline failed with exit code {exit_code}"
        
        async with db_pool.acquire() as conn:
            await update_pipeline_status(conn, pipeline_id, status, error_msg, exit_code)
            
            # Update Nextflow execution with final status
            nxf_status = 'succeeded' if exit_code == 0 else 'failed'
            await update_nextflow_execution_status(
                conn, execution_id, nxf_status, exit_code, error_msg
            )
        
        # If successful, upload results to MinIO
        if exit_code == 0:
            logger.info(f"Pipeline {pipeline_id} completed successfully, uploading results to MinIO")
            asyncio.create_task(upload_results_to_minio(app, pipeline_id, sample_code, results_path))
        
        # Cleanup temp files
        try:
            import shutil
            shutil.rmtree(work_dir_path)
            logger.info(f"✓ Cleaned up temp directory: {work_dir_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp directory: {e}")
        
        logger.info(f"Pipeline {pipeline_id} finished with status: {status}")
        
    except Exception as e:
        logger.error(f"Pipeline execution error: {str(e)}", exc_info=True)
        async with db_pool.acquire() as conn:
            await update_pipeline_status(conn, pipeline_id, 'failed', str(e), -1)
            await update_nextflow_execution_status(conn, execution_id, 'failed', -1, str(e))


async def upload_results_to_minio(app, pipeline_id, sample_code, results_path):
    """
    Upload pipeline results to Silver and Gold layers in MinIO
    
    Silver: All intermediate results organized by process
    Gold: Curated final results (best assemblies, high-quality bins)
    """
    db_pool = await get_db_pool(app)
    minio_client = get_minio_client()
    
    try:
        logger.info(f"Starting lakehouse upload for sample {sample_code}")
        
        async with db_pool.acquire() as conn:
            # Track Silver upload start
            await track_progress(
                conn, pipeline_id, 'silver_upload',
                'Starting Silver layer upload (intermediate results)',
                'in_progress', 0
            )
            
            # Get execution_id and sample_id
            row = await conn.fetchrow("""
                SELECT nextflow_execution_id, sample_id 
                FROM pipeline_runs 
                WHERE pipeline_id = $1
            """, pipeline_id)
            
            execution_id = row['nextflow_execution_id']
            sample_id = row['sample_id']
            
            # Update silver_path with actual run_id
            silver_path = f"genomic-silver/{sample_code}/{pipeline_id}/"
            await conn.execute(
                "UPDATE pipeline_runs SET silver_path = $1 WHERE pipeline_id = $2",
                silver_path, pipeline_id
            )
        
        results_dir = Path(results_path)
        silver_uploads = 0
        
        # ==================== SILVER LAYER UPLOAD ====================
        # Upload results from each process to silver layer
        
        process_mappings = {
            '01_QC/nanoplot': ('NANOPLOT', None),
            '02_filtered': ('FILTLONG', None),
            '03_assembly': ('FLYE', None),
            '04_binning/metabat2': ('METABAT2', None),
            '04_binning/concoct': ('CONCOCT', None),
            '05_quality/metabat2': ('CHECKM_METABAT2', None),
            '05_quality/concoct': ('CHECKM_CONCOCT', None),
            '06_kraken2': ('KRAKEN2', None),
            '07_bracken': ('BRACKEN', None),
        }
        
        total_processes = len(process_mappings)
        completed_processes = 0
        
        for dir_pattern, (process_name, tool_version) in process_mappings.items():
            process_dir = results_dir / dir_pattern
            
            if not process_dir.exists():
                logger.warning(f"Process directory not found: {process_dir}")
                completed_processes += 1
                continue
            
            # Collect all files in this process directory
            process_files = []
            for file_path in process_dir.rglob('*'):
                if file_path.is_file():
                    process_files.append(str(file_path))
            
            if not process_files:
                logger.warning(f"No files found in {process_dir}")
                completed_processes += 1
                continue
            
            # Track process upload
            async with db_pool.acquire() as conn:
                await track_progress(
                    conn, pipeline_id, 'silver_upload',
                    f'Uploading {process_name} results to Silver',
                    'in_progress', int((completed_processes / total_processes) * 100),
                    {'process': process_name, 'file_count': len(process_files)}
                )
            
            # Upload to silver layer
            async with db_pool.acquire() as conn:
                object_ids = await upload_to_silver(
                    conn, minio_client, sample_code, str(pipeline_id),
                    process_name, process_files, execution_id, tool_version
                )
                silver_uploads += len(object_ids)
                logger.info(f"✓ Uploaded {len(object_ids)} files from {process_name} to silver layer")
            
            completed_processes += 1
        
        # Upload logs to silver layer
        log_files = []
        for log_file in ['nextflow.log', 'nextflow_trace.txt', 'nextflow_timeline.html', 'nextflow_report.html']:
            log_path = results_dir / log_file
            if log_path.exists():
                log_files.append(str(log_path))
        
        if log_files:
            async with db_pool.acquire() as conn:
                object_ids = await upload_to_silver(
                    conn, minio_client, sample_code, str(pipeline_id),
                    'LOGS', log_files, execution_id, None
                )
                silver_uploads += len(object_ids)
                logger.info(f"✓ Uploaded {len(object_ids)} log files to silver layer")
        
        # Track Silver completion
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'silver_upload',
                f'✓ Silver upload complete: {silver_uploads} files uploaded',
                'completed', 100,
                {
                    'total_files': silver_uploads,
                    'processes': list(process_mappings.keys()),
                    'silver_path': silver_path
                }
            )
        
        logger.info(f"✓ Silver layer upload complete: {silver_uploads} files uploaded")
        
        # ==================== GOLD LAYER CURATION ====================
        # Curate and upload final results to gold layer
        
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'gold_curation',
                'Starting Gold layer curation (high-quality results)',
                'in_progress', 0
            )
        
        logger.info(f"Starting gold layer curation for pipeline {pipeline_id}")
        
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'gold_curation',
                'Analyzing assembly metrics and bin quality',
                'in_progress', 30
            )
            
            summary = await curate_gold_layer(
                conn, minio_client, pipeline_id, sample_code, results_path
            )
            
            # Track Gold completion
            await track_progress(
                conn, pipeline_id, 'gold_curation',
                f'✓ Gold curation complete: {summary.get("high_quality_bins", 0)} high-quality bins',
                'completed', 100,
                {
                    'high_quality_bins': summary.get('high_quality_bins', 0),
                    'medium_quality_bins': summary.get('medium_quality_bins', 0),
                    'low_quality_bins': summary.get('low_quality_bins', 0),
                    'assemblies': summary.get('assemblies_count', 0),
                    'total_artifacts': summary.get('total_bins', 0) + summary.get('assemblies_count', 0)
                }
            )
        
        logger.info(f"✓ Gold layer curation complete")
        logger.info(f"  High-quality bins: {summary.get('high_quality_bins', 0)}")
        logger.info(f"  Total artifacts in gold: {summary.get('total_bins', 0) + summary.get('assemblies_count', 0)}")
        
        # Track overall completion
        async with db_pool.acquire() as conn:
            await track_progress(
                conn, pipeline_id, 'cleanup',
                '✓ Pipeline completed successfully',
                'completed', 100,
                {
                    'silver_files': silver_uploads,
                    'gold_artifacts': summary.get('total_bins', 0) + summary.get('assemblies_count', 0)
                }
            )
        
        logger.info(f"✓ Lakehouse upload complete for sample {sample_code}")
        logger.info(f"  Silver: {silver_uploads} files")
        logger.info(f"  Gold: {summary.get('high_quality_bins', 0)} high-quality bins + {summary.get('assemblies_count', 0)} assemblies")
        
    except Exception as e:
        logger.error(f"Error in lakehouse upload: {e}", exc_info=True)
        
        # Track error
        try:
            async with db_pool.acquire() as conn:
                await track_progress(
                    conn, pipeline_id, 'silver_upload',
                    f'Failed: {str(e)}',
                    'failed', 0
                )
        except Exception:
            pass


# Register blueprint
def setup_routes(app):
    """Setup pipeline routes"""
    app.blueprint(pipeline_bp)
    logger.info("Pipeline routes registered")

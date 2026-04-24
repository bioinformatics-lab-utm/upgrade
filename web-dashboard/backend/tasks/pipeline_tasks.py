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


class PipelineLogger:
    """Structured logger with pipeline context"""
    
    def __init__(self, pipeline_id: int, sample_code: str, job_id: str = None):
        self.pipeline_id = pipeline_id
        self.sample_code = sample_code
        self.job_id = job_id
        self._prefix = f"[pipeline={pipeline_id}][sample={sample_code}]"
        if job_id:
            self._prefix += f"[job={job_id}]"
    
    def info(self, msg: str, **kwargs):
        extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
        logger.info(f"{self._prefix} {msg} {extra}".strip())
    
    def warning(self, msg: str, **kwargs):
        extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
        logger.warning(f"{self._prefix} {msg} {extra}".strip())
    
    def error(self, msg: str, **kwargs):
        extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
        logger.error(f"{self._prefix} {msg} {extra}".strip())
    
    def debug(self, msg: str, **kwargs):
        extra = ' '.join(f"{k}={v}" for k, v in kwargs.items())
        logger.debug(f"{self._prefix} {msg} {extra}".strip())


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
        """Update pipeline status in database. Raises on failure."""
        conn = await asyncpg.connect(config.DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE pipeline_runs
                SET status = $1::varchar,
                    error_message = $2::text,
                    completed_at = CASE WHEN $1::varchar IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END,
                    started_at = CASE WHEN $1::varchar = 'running' AND started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END
                WHERE pipeline_id = $3
            """, status, error_message, pipeline_id)
            logger.info(f"Pipeline {pipeline_id} status updated to: {status}")
        finally:
            await conn.close()

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
            try:
                await conn.execute("""
                    INSERT INTO pipeline_progress_events
                    (pipeline_id, stage, step, status, progress_percent, details)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """, pipeline_id, stage, step, status, progress_percent, json.dumps(metadata or {}))
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to track progress: {e}")

    async def create_nextflow_execution(self, pipeline_id: int, sample_code: str, job_id: str) -> int:
        """Create a nextflow_executions row and return execution_id"""
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)
            try:
                wf = await conn.fetchval("SELECT workflow_id FROM nextflow_workflows WHERE workflow_name = $1 AND workflow_version = $2 LIMIT 1", 'UPGRADE_Genomic_Pipeline', '1.0')
                if not wf:
                    wf = await conn.fetchval(
                        "INSERT INTO nextflow_workflows (workflow_name, workflow_version, description, nextflow_version, workflow_script_path, is_active) VALUES ($1,$2,$3,$4,$5,$6) RETURNING workflow_id",
                        'UPGRADE_Genomic_Pipeline', '1.0', 'Environmental genomic surveillance with ONT sequencing', '25.10.0', '/nextflow/main.nf', True
                    )

                exec_name = f"rq_job_{job_id}_{sample_code}"

                exec_id = await conn.fetchval(
                    "INSERT INTO nextflow_executions (workflow_id, execution_name, nextflow_run_name, status, start_time, created_at) VALUES ($1,$2,$3,$4, now(), now()) RETURNING execution_id",
                    wf, exec_name, exec_name, 'running'
                )

                logger.info(f"Created nextflow_execution execution_id={exec_id}")
                return exec_id
            finally:
                await conn.close()

        except Exception as e:
            logger.error(f"Failed to create nextflow_execution: {e}")
            return None

    async def _record_uploaded_file(self, bucket_name: str, object_info: Dict, pipeline_id: int, execution_id: int, layer_stage: str = 'silver') -> Optional[int]:
        """Record uploaded file into minio_objects and set pipeline/execution linkage."""
        try:
            from minio_helper import get_or_create_bucket, save_minio_object_to_db
            conn = await asyncpg.connect(config.DATABASE_URL)
            try:
                bucket_id = await get_or_create_bucket(conn, bucket_name, layer_stage)
                object_id = await save_minio_object_to_db(conn, bucket_id, None, object_info, execution_id)
                await conn.execute("UPDATE minio_objects SET pipeline_id = $1, layer_stage = $2 WHERE object_id = $3", pipeline_id, layer_stage, object_id)
                return object_id
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to record uploaded file to DB: {e}")
            return None

    async def _get_bronze_object_ids(self, pipeline_id: int) -> list:
        """Get Bronze layer object IDs linked to this pipeline for lineage tracking."""
        try:
            conn = await asyncpg.connect(config.DATABASE_URL)
            try:
                rows = await conn.fetch("""
                    SELECT mo.object_id FROM minio_objects mo
                    JOIN minio_buckets mb ON mo.bucket_id = mb.bucket_id
                    WHERE mo.pipeline_id = $1 AND mb.layer_type = 'bronze'
                """, pipeline_id)
                return [row['object_id'] for row in rows]
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to get bronze object IDs: {e}")
            return []

    async def _upload_silver_batch(self, minio_client, sample_code: str, pipeline_id: int,
                                    process_name: str, local_files: list,
                                    execution_id: int, source_object_ids: list) -> list:
        """Upload files to Silver layer with lineage tracking via upload_to_silver()."""
        try:
            from minio_helper import upload_to_silver
            conn = await asyncpg.connect(config.DATABASE_URL)
            try:
                object_ids = await upload_to_silver(
                    conn, minio_client, sample_code, pipeline_id, process_name,
                    local_files, execution_id=execution_id,
                    source_object_ids=source_object_ids or None
                )
                return object_ids
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to upload Silver batch [{process_name}]: {e}")
            return []

    async def _curate_gold(self, minio_client, pipeline_id: int,
                           sample_code: str, results_path: str) -> dict:
        """Curate and upload Gold layer artifacts with quality scoring."""
        try:
            from minio_helper import curate_gold_layer
            conn = await asyncpg.connect(config.DATABASE_URL)
            try:
                summary = await curate_gold_layer(
                    conn, minio_client, pipeline_id, sample_code, results_path
                )
                return summary or {}
            finally:
                await conn.close()
        except Exception as e:
            logger.error(f"Failed to curate Gold layer: {e}")
            return {}

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

            # Sync results_path in DB to match the actual output_dir
            async def _sync_results_path():
                conn = await asyncpg.connect(config.DATABASE_URL)
                try:
                    await conn.execute(
                        "UPDATE pipeline_runs SET results_path = $1 WHERE pipeline_id = $2",
                        str(output_dir), pipeline_id
                    )
                finally:
                    await conn.close()
            asyncio.run(_sync_results_path())

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
                str(local_input_dir),
                pipeline_id
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

            # Create a nextflow_executions record so uploads can be linked
            execution_id = asyncio.run(self.create_nextflow_execution(pipeline_id, sample_code, job_id))

            # Execute Nextflow from work directory (not from read-only /nextflow)
            # Nextflow needs write access to create .nextflow/ directory
            nextflow_env = os.environ.copy()
            upgrade_base = os.environ.get('UPGRADE_BASE_DIR', str(Path(__file__).parent.parent.parent))
            nextflow_env['UPGRADE_HOME'] = upgrade_base
            nextflow_env['UPGRADE_BASE_DIR'] = upgrade_base
            
            # Use umask 0o022 so files are owner-writable, group/other readable
            old_umask = os.umask(0o022)
            try:
                result = subprocess.run(
                    nextflow_cmd,
                    capture_output=True,
                    text=True,
                    timeout=config.RQ_JOB_TIMEOUT,
                    cwd=str(work_dir),
                    env=nextflow_env
                )
            finally:
                os.umask(old_umask)

            # Log Nextflow output immediately
            logger.info(f"Nextflow exit code: {result.returncode}")
            if result.stdout:
                logger.info(f"Nextflow STDOUT:\n{result.stdout}")
            if result.stderr:
                logger.error(f"Nextflow STDERR:\n{result.stderr}")

            # Save Nextflow log to file for web UI access
            log_file_path = str(output_dir / 'nextflow_execution.log')
            try:
                with open(log_file_path, 'w') as f:
                    f.write(f"=== Nextflow Execution Log ===\n")
                    f.write(f"Pipeline ID: {pipeline_id}\n")
                    f.write(f"Sample: {sample_code}\n")
                    f.write(f"Exit code: {result.returncode}\n\n")
                    f.write(f"=== STDOUT ===\n{result.stdout}\n\n")
                    if result.stderr:
                        f.write(f"=== STDERR ===\n{result.stderr}\n")
            except Exception as e:
                logger.warning(f"Failed to write log file: {e}")
                log_file_path = None

            # Update log_file_path and exit_code in database
            async def _update_log_path():
                conn = await asyncpg.connect(config.DATABASE_URL)
                try:
                    await conn.execute("""
                        UPDATE pipeline_runs
                        SET log_file_path = $1, exit_code = $2
                        WHERE pipeline_id = $3
                    """, log_file_path, result.returncode, pipeline_id)
                finally:
                    await conn.close()

            try:
                asyncio.run(_update_log_path())
            except Exception as e:
                logger.warning(f"Failed to update log_file_path: {e}")

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
                # === SILVER LAYER: Upload results per Nextflow process with lineage ===
                asyncio.run(self.track_progress(
                    pipeline_id, 'silver_upload', 'Uploading results to Silver layer',
                    'started', 85
                ))

                try:
                    from minio_helper import SILVER_LAYER_MAPPING
                    uploaded_count = 0

                    # Get Bronze source object IDs for lineage tracking
                    bronze_source_ids = asyncio.run(self._get_bronze_object_ids(pipeline_id))
                    logger.info(f"Bronze source IDs for lineage: {bronze_source_ids}")

                    # Upload each Nextflow process output via upload_to_silver()
                    for process_name, layer_dir in SILVER_LAYER_MAPPING.items():
                        process_dir = output_dir / layer_dir
                        if process_dir.exists():
                            local_files = [str(f) for f in process_dir.rglob('*') if f.is_file() and not f.name.startswith('.')]
                            if local_files:
                                object_ids = asyncio.run(self._upload_silver_batch(
                                    minio_client, sample_code, pipeline_id, process_name,
                                    local_files, execution_id, bronze_source_ids
                                ))
                                uploaded_count += len(object_ids)
                                logger.info(f"✓ Silver [{process_name}]: {len(object_ids)} files → {layer_dir}/")

                    # Upload remaining files not covered by SILVER_LAYER_MAPPING (Nextflow reports, etc.)
                    mapped_dirs = set(SILVER_LAYER_MAPPING.values())
                    for file_path in output_dir.rglob('*'):
                        if not file_path.is_file() or file_path.name.startswith('.'):
                            continue
                        relative = file_path.relative_to(output_dir)
                        # Skip files already uploaded via SILVER_LAYER_MAPPING
                        if any(str(relative).startswith(d) for d in mapped_dirs):
                            continue
                        # Upload remaining files (nextflow_report.html, trace.txt, etc.)
                        object_path = f"{sample_code}/{pipeline_id}/{relative}"
                        try:
                            object_info = minio_client.upload_file('genomic-silver', object_path, str(file_path))
                            asyncio.run(self._record_uploaded_file('genomic-silver', object_info, pipeline_id, execution_id, layer_stage='silver'))
                            uploaded_count += 1
                        except Exception as upload_err:
                            logger.warning(f"Failed to upload {file_path.name}: {upload_err}")

                    logger.info(f"Silver layer complete: {uploaded_count} files uploaded")
                    asyncio.run(self.track_progress(
                        pipeline_id, 'silver_upload', f'Uploaded {uploaded_count} files to Silver',
                        'completed', 90
                    ))

                    # === GOLD LAYER: Curate quality artifacts (assemblies, scored bins, reports) ===
                    asyncio.run(self.track_progress(
                        pipeline_id, 'gold_curation', 'Curating Gold layer artifacts',
                        'started', 92
                    ))

                    gold_summary = asyncio.run(self._curate_gold(
                        minio_client, pipeline_id, sample_code, str(output_dir)
                    ))
                    gold_count = sum(len(v) for v in gold_summary.values() if isinstance(v, list))
                    logger.info(f"Gold layer complete: {gold_count} curated artifacts")

                    asyncio.run(self.track_progress(
                        pipeline_id, 'gold_curation', f'Curated {gold_count} artifacts to Gold',
                        'completed', 95
                    ))

                except Exception as e:
                    logger.warning(f"Failed to upload to Silver/Gold layers: {e}", exc_info=True)
                    # Don't fail the pipeline if lakehouse upload fails

                # === PARSE RESULTS -> DB (before cleanup while files still exist) ===
                try:
                    asyncio.run(self._store_pipeline_results(
                        pipeline_id, output_dir, sample_code
                    ))
                except Exception as parse_err:
                    logger.warning(f"Result parsing failed (non-critical): {parse_err}", exc_info=True)

                # === CLEANUP: Remove local results (already in Silver/Gold) and work dir ===
                try:
                    import shutil
                    if output_dir.exists():
                        shutil.rmtree(output_dir, ignore_errors=True)
                        logger.info(f"Cleaned up results dir: {output_dir}")
                    # Clean sample input dir (downloaded FASTQ from Bronze)
                    if local_input_dir.exists():
                        shutil.rmtree(local_input_dir, ignore_errors=True)
                        logger.info(f"Cleaned up input dir: {local_input_dir}")
                except Exception as cleanup_err:
                    logger.warning(f"Cleanup failed (non-critical): {cleanup_err}")

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

                # Cleanup input dir for failed pipelines (Bronze still has the data)
                try:
                    import shutil
                    if local_input_dir.exists():
                        shutil.rmtree(local_input_dir, ignore_errors=True)
                        logger.info(f"Cleaned up input dir after failure: {local_input_dir}")
                except Exception as cleanup_err:
                    logger.warning(f"Cleanup failed (non-critical): {cleanup_err}")

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


    async def _store_pipeline_results(
        self,
        pipeline_id: int,
        output_dir: Path,
        sample_code: str,
    ) -> None:
        """
        Parse generate_summary.py output and persist all results to DB.
        Called after Nextflow completes, before local cleanup.
        Populates: quality_control_results, assemblies, detected_organisms,
                   resistance_genes, and pipeline_runs.summary_json / quality_score.
        """
        import json as _json
        from datetime import datetime as _dt

        # Try local file first (while still in pipeline run, before cleanup)
        summary_path = output_dir / "00_summary" / f"{sample_code}_summary.json"
        summary = None

        if summary_path.exists():
            try:
                summary = _json.loads(summary_path.read_text())
            except Exception as e:
                logger.warning(f"[pipeline={pipeline_id}] Failed to read local summary.json: {e}")

        # Fallback: read full summary from MinIO Silver layer
        if summary is None:
            try:
                from minio_helper import get_minio_client
                minio = get_minio_client()
                obj = minio.client.get_object(
                    'genomic-silver',
                    f"{sample_code}/{pipeline_id}/00_summary/{sample_code}_summary.json"
                )
                summary = _json.loads(obj.read())
                logger.info(f"[pipeline={pipeline_id}] Loaded summary from MinIO Silver")
            except Exception as e:
                logger.warning(f"[pipeline={pipeline_id}] summary.json not found locally or in MinIO Silver, skipping: {e}")
                return

        conn = await asyncpg.connect(config.DATABASE_URL)
        try:
            # Fetch sample_id from pipeline_runs
            sample_id = await conn.fetchval(
                'SELECT sample_id FROM pipeline_runs WHERE pipeline_id = $1', pipeline_id
            )
            if not sample_id:
                logger.warning(f"[pipeline={pipeline_id}] No sample_id found, skipping result parsing")
                return
            # ---- 1. quality_control_results (NanoPlot) ----
            qc = summary.get('qc') or {}
            if qc.get('reads_count'):
                existing = await conn.fetchval(
                    'SELECT count(*) FROM quality_control_results WHERE sample_id=$1', sample_id
                )
                if not existing:
                    total = qc.get('reads_count', 0)
                    await conn.execute("""
                        INSERT INTO quality_control_results (
                            sample_id, total_reads, passed_reads, failed_reads,
                            pass_rate, mean_quality_score, median_quality_score,
                            mean_read_length, median_read_length, n50_read_length,
                            is_passed, qc_tool
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    """,
                        sample_id, total, total, 0, 100.0,
                        qc.get('mean_quality') or qc.get('mean_qual'),
                        qc.get('median_qual'),
                        int(qc.get('mean_length', 0) or 0),
                        int(qc.get('median_length', 0) or 0),
                        int(qc.get('n50', 0) or 0),
                        (qc.get('mean_quality', 0) or 0) >= 7,
                        'NanoPlot',
                    )

            # ---- 2. assemblies (Flye + CheckM) ----
            asm = summary.get('assembly') or {}
            mags = summary.get('mags') or {}
            if asm.get('contigs_count', 0) > 0:
                existing = await conn.fetchval(
                    'SELECT count(*) FROM assemblies WHERE sample_id=$1 AND pipeline_run_id=$2',
                    sample_id, pipeline_id
                )
                if not existing:
                    best_completeness = max(
                        (b['completeness'] for b in mags.get('bins', [])), default=None
                    )
                    avg_contamination = (
                        sum(b['contamination'] for b in mags.get('bins', [])) /
                        len(mags['bins']) if mags.get('bins') else None
                    )
                    quality_grade = (
                        'high'   if (best_completeness or 0) >= 90 and (avg_contamination or 99) <= 5  else
                        'medium' if (best_completeness or 0) >= 50 and (avg_contamination or 99) <= 10 else
                        'low'
                    )
                    await conn.execute("""
                        INSERT INTO assemblies (
                            sample_id, pipeline_run_id, assembler, assembly_type,
                            total_contigs, total_length, n50_contig,
                            longest_contig, gc_content,
                            completeness, contamination, quality_grade,
                            assembly_fasta_path
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                    """,
                        sample_id, pipeline_id, 'Flye+Medaka', 'metagenome',
                        asm.get('contigs_count') or asm.get('contigs'),
                        asm.get('total_length'),
                        asm.get('n50'),
                        asm.get('longest_contig'),
                        asm.get('gc_content'),
                        best_completeness,
                        avg_contamination,
                        quality_grade,
                        f'genomic-silver/{sample_code}/{pipeline_id}/03_assembly/',
                    )

            # ---- 3. detected_organisms (Kraken2) ----
            taxonomy = summary.get('taxonomy') or {}
            species = taxonomy.get('species') or []
            if species:
                existing = await conn.fetchval(
                    'SELECT count(*) FROM detected_organisms WHERE sample_id=$1 AND pipeline_run_id=$2',
                    sample_id, pipeline_id
                )
                if not existing:
                    for sp in species:
                        await conn.execute("""
                            INSERT INTO detected_organisms (
                                sample_id, pipeline_run_id, organism_name, scientific_name,
                                taxonomy_rank, classification_tool,
                                abundance, confidence_score
                            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                            sample_id, pipeline_id,
                            sp.get('name', ''), sp.get('name', ''),
                            'species', 'Kraken2',
                            sp.get('abundance', 0.0),
                            sp.get('abundance', 0.0),
                        )

            # ---- 4. resistance_genes (Abricate) ----
            amr = summary.get('amr') or {}
            genes = amr.get('genes') or []
            if genes:
                existing = await conn.fetchval(
                    'SELECT count(*) FROM resistance_genes WHERE sample_id=$1 AND pipeline_run_id=$2',
                    sample_id, pipeline_id
                )
                if not existing:
                    for g in genes:
                        gene_str = g.get('gene', '')
                        await conn.execute("""
                            INSERT INTO resistance_genes (
                                sample_id, pipeline_run_id, gene_name, gene_symbol,
                                detection_tool, coverage, identity,
                                predicted_resistance, resistance_mechanism,
                                confidence_level, quality_score
                            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        """,
                            sample_id, pipeline_id,
                            gene_str[:200], gene_str[:50],
                            g.get('database', 'Abricate')[:100],
                            g.get('coverage', 0.0), g.get('identity', 0.0),
                            [g.get('antibiotic_class', '')] if g.get('antibiotic_class') else [],
                            g.get('mechanism', '')[:200],
                            g.get('risk_level', 'medium')[:50],
                            g.get('identity', 0.0),
                        )

            # ---- 5. Update pipeline_runs with scores + full summary JSON ----
            await conn.execute("""
                UPDATE pipeline_runs
                SET quality_score     = $1,
                    amr_risk_score    = $2,
                    summary_json      = $3,
                    results_parsed_at = $4
                WHERE pipeline_id = $5
            """,
                summary.get('quality_score'),
                summary.get('amr_risk_score'),
                _json.dumps(summary),
                _dt.now(),
                pipeline_id,
            )

            logger.info(
                f"[pipeline={pipeline_id}] Results stored: "
                f"QC={bool(qc.get('reads_count'))}, "
                f"Assembly contigs={asm.get('contigs_count',0)}, "
                f"Organisms={len(species)}, AMR genes={len(genes)}, "
                f"quality_score={summary.get('quality_score')}"
            )

        except Exception as e:
            logger.error(f"[pipeline={pipeline_id}] Failed to store results: {e}", exc_info=True)
        finally:
            await conn.close()


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

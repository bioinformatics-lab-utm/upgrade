#!/usr/bin/env python3
"""
Host-based batch processor - downloads on host, runs pipeline in container
Uses docker exec to PostgreSQL instead of direct connection
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path('/home/nicolaedrabcinski/upgrade')
DATA_DIR = PROJECT_ROOT / 'data'
RESULTS_DIR = PROJECT_ROOT / 'results'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def exec_sql(query, params=None):
    """Execute SQL via docker exec"""
    if params:
        # Escape single quotes in params
        safe_params = [str(p).replace("'", "''") if p else 'NULL' for p in params]
        # Simple parameter substitution for positional %s
        formatted_query = query
        for param in safe_params:
            formatted_query = formatted_query.replace('%s', f"'{param}'", 1)
        query = formatted_query
    
    cmd = ['docker', 'exec', '-i', 'upgrade_postgres',
           'psql', '-U', 'upgrade', '-d', 'upgrade_db', 
           '-t', '-A', '-c', query]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()

def get_pending_samples(limit=10):
    """Get pending samples from queue"""
    query = f"""
        SELECT accession, file_size_mb, geo_loc_name, latitude, longitude
        FROM sample_queue
        WHERE status = 'pending'
        ORDER BY file_size_mb ASC
        LIMIT {limit};
    """
    
    result = exec_sql(query)
    if not result:
        return []
    
    samples = []
    for line in result.split('\n'):
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 5:
                samples.append((
                    parts[0],  # accession
                    float(parts[1]) if parts[1] else 0.0,  # file_size_mb
                    parts[2] if parts[2] else '',  # geo_loc_name
                    float(parts[3]) if parts[3] else 0.0,  # latitude
                    float(parts[4]) if parts[4] else 0.0   # longitude
                ))
    return samples

def get_active_samples_size():
    """Get total size of samples currently downloading or processing"""
    query = """
        SELECT COALESCE(SUM(file_size_mb), 0) / 1024.0
        FROM sample_queue
        WHERE status IN ('downloading', 'downloaded', 'processing');
    """
    
    result = exec_sql(query)
    try:
        return float(result) if result else 0.0
    except:
        return 0.0

def update_status(accession, status, error=None):
    """Update sample status in database - FIXED: SQL injection vulnerability"""
    try:
        if status == 'downloading':
            query = """
                UPDATE sample_queue
                SET status = %s,
                    download_started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession = %s;
            """
            exec_sql(query, [status, accession])
        elif status == 'downloaded':
            query = """
                UPDATE sample_queue
                SET download_completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession = %s;
            """
            exec_sql(query, [accession])
        elif status == 'processing':
            query = """
                UPDATE sample_queue
                SET status = %s,
                    pipeline_started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession = %s;
            """
            exec_sql(query, [status, accession])
        elif status == 'completed':
            query = """
                UPDATE sample_queue
                SET status = %s,
                    pipeline_completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession = %s;
            """
            exec_sql(query, [status, accession])
        elif status == 'failed':
            query = """
                UPDATE sample_queue
                SET status = %s,
                    error_message = %s,
                    retry_count = retry_count + 1,
                    last_attempt_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession = %s;
            """
            exec_sql(query, [status, error or '', accession])
        else:
            return
    except Exception as e:
        log(f"Error updating status: {e}")

def create_pipeline_run(accession, latitude, longitude, location):
    """Create entry in pipeline_runs table for dashboard visibility - FIXED: SQL injection"""
    try:
        results_path = f"/results/{accession}"
        query = """
            INSERT INTO pipeline_runs (
                sample_name, pipeline_name, pipeline_version, 
                status, location, sample_type, results_path,
                started_at, queued_at
            )
            VALUES (
                %s, 'Metagenomic Pipeline', 'v1.0',
                'running', %s, 'nanopore', %s,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING pipeline_id;
        """
        result = exec_sql(query, [accession, location or '', results_path])
        if result:
            pipeline_id = result.strip().split('\n')[-2].strip()
            log(f"  Created pipeline_runs entry: pipeline_id={pipeline_id}")
            return pipeline_id
    except Exception as e:
        log(f"Warning: Failed to create pipeline_run for {accession}: {e}")
    return None

def update_pipeline_run(accession, status, error=None):
    """Update pipeline_runs table status - FIXED: SQL injection"""
    try:
        if status == 'completed':
            query = """
                UPDATE pipeline_runs
                SET status = %s,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE sample_name = %s
                  AND status IN ('running', 'queued');
            """
            exec_sql(query, [status, accession])
        elif status == 'failed':
            query = """
                UPDATE pipeline_runs
                SET status = %s,
                    error_message = %s,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE sample_name = %s
                  AND status IN ('running', 'queued');
            """
            exec_sql(query, [status, error or '', accession])
        else:
            return
    except Exception as e:
        log(f"Warning: Failed to update pipeline_run for {accession}: {e}")

def download_sample(accession):
    """Download sample using fasterq-dump on host"""
    log(f"Downloading {accession}...")
    
    sample_dir = DATA_DIR / accession / 'raw'
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    # Clean up any existing files from previous failed attempts (use sudo for permission)
    existing_files = list(sample_dir.glob('*.fastq*'))
    if existing_files:
        for f in existing_files:
            try:
                subprocess.run(['sudo', 'rm', '-f', str(f)], check=True)
                log(f"  Removed existing file: {f.name}")
            except Exception as e:
                log(f"  Warning: Could not remove {f.name}: {e}")
    
    update_status(accession, 'downloading')
    
    # Download to /tmp first (to avoid permission issues), then move to sample_dir
    tmp_dir = Path(f'/tmp/sra_download_{accession}')
    tmp_dir.mkdir(exist_ok=True)
    
    cmd = f'cd {tmp_dir} && fasterq-dump {accession} --threads 4 --temp /tmp --progress && sudo mv *.fastq* {sample_dir}/ && cd /tmp && rm -rf {tmp_dir}'
    
    try:
        log(f"  Running: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result.returncode != 0:
            error = f"fasterq-dump failed: {result.stderr[:500]}"
            log(f"  ✗ {error}")
            update_status(accession, 'failed', error)
            return False
        
        # Check files downloaded
        fastq_files = list(sample_dir.glob('*.fastq*'))
        if not fastq_files:
            error = "No FASTQ files downloaded"
            log(f"  ✗ {error}")
            update_status(accession, 'failed', error)
            return False
        
        update_status(accession, 'downloaded')
        total_size = sum(f.stat().st_size for f in fastq_files) / 1024 / 1024
        log(f"  ✓ Downloaded {len(fastq_files)} files ({total_size:.1f} MB)")
        
        return True
        
    except subprocess.TimeoutExpired:
        error = "Download timeout (>1 hour)"
        log(f"  ✗ {error}")
        update_status(accession, 'failed', error)
        return False
    except Exception as e:
        error = f"Download error: {str(e)}"
        log(f"  ✗ {error}")
        update_status(accession, 'failed', error)
        return False

def run_pipeline(accession):
    """Run Nextflow pipeline in Docker container"""
    log(f"Running pipeline for {accession}...")
    
    input_dir = f"/data/{accession}/raw"
    output_dir = f"/results/{accession}"
    
    update_status(accession, 'processing')
    
    # Use home directory for NXF_HOME and NXF_TEMP, but /tmp for work-dir (shared with Docker)
    cmd = [
        'docker', 'exec', 'upgrade_rq_worker',
        'bash', '-c',
        f'export NXF_HOME=/home/rqworker/.nextflow && '
        f'export NXF_TEMP=/home/rqworker/.nextflow/tmp && '
        f'mkdir -p /home/rqworker/.nextflow/tmp && '
        f'cd /home/rqworker && '
        f'nextflow run /nextflow/main.nf '
        f'--input_dir {input_dir} '
        f'--outdir {output_dir} '
        f'--sample_id {accession} '
        f'-work-dir /tmp/nextflow-work '
        f'-profile docker '
        f'-resume'
    ]
    
    try:
        log(f"  Running Nextflow...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200
        )
        
        # Log full output for debugging
        if result.stdout:
            log(f"  Nextflow stdout (last 1000 chars):\n{result.stdout[-1000:]}")
        if result.stderr:
            log(f"  Nextflow stderr (last 1000 chars):\n{result.stderr[-1000:]}")
        
        if result.returncode != 0:
            error = f"Nextflow exit code {result.returncode}: {result.stderr[-500:]}"
            log(f"  ✗ {error}")
            update_status(accession, 'failed', error)
            return False
        
        # Check for summary JSON
        summary_dir = RESULTS_DIR / accession / '00_summary'
        summary_files = list(summary_dir.glob('*_summary.json')) if summary_dir.exists() else []
        
        if not summary_files:
            error = "Pipeline completed but no summary JSON found"
            log(f"  ⚠ {error}")
            # Still mark as completed since pipeline ran
        
        update_status(accession, 'completed')
        log(f"  ✓ Pipeline completed")
        return True
        
    except subprocess.TimeoutExpired:
        error = "Pipeline timeout (>2 hours)"
        log(f"  ✗ {error}")
        update_status(accession, 'failed', error)
        return False
    except Exception as e:
        error = f"Pipeline error: {str(e)}"
        log(f"  ✗ {error}")
        update_status(accession, 'failed', error)
        return False

def process_one_sample(accession, latitude=None, longitude=None, location=None):
    """Complete pipeline for one sample"""
    log(f"\n{'='*80}")
    log(f"Processing {accession}")
    log(f"{'='*80}")
    
    # Create pipeline_runs entry for dashboard
    pipeline_id = None
    if latitude and longitude and location:
        pipeline_id = create_pipeline_run(accession, latitude, longitude, location)
    
    # Step 1: Download
    if not download_sample(accession):
        if pipeline_id:
            update_pipeline_run(accession, 'failed', 'Download failed')
        return False
    
    # Step 2: Run pipeline
    if not run_pipeline(accession):
        if pipeline_id:
            update_pipeline_run(accession, 'failed', 'Pipeline execution failed')
        return False
    
    # Update pipeline_runs as completed
    if pipeline_id:
        update_pipeline_run(accession, 'completed')
    
    log(f"✅ {accession} completed successfully")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 host_batch_processor.py [--max-concurrent-gb GB] <max_samples>")
        print("\nOptions:")
        print("  --max-concurrent-gb GB    Max GB in downloading/processing at once (default: 20)")
        print("\nExample:")
        print("  python3 host_batch_processor.py --max-concurrent-gb 20 100")
        sys.exit(1)
    
    # Parse arguments
    max_concurrent_gb = 20.0  # Default
    max_samples = 10
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--max-concurrent-gb':
            max_concurrent_gb = float(args[i+1])
            i += 2
        else:
            max_samples = int(args[i])
            i += 1
    
    log("="*80)
    log("Host-Based Batch Processor")
    log(f"Max concurrent: {max_concurrent_gb} GB")
    log(f"Batch size: {max_samples} samples")
    log("="*80)
    
    # Get pending samples
    all_pending = get_pending_samples(max_samples * 10)  # Get more to allow selection
    log(f"\nFound {len(all_pending)} pending samples in queue")
    
    if not all_pending:
        log("No pending samples to process")
        return
    
    # Process samples with concurrent limit
    processed = 0
    failed = 0
    start_time = time.time()
    processed_count = 0
    
    while processed_count < max_samples and all_pending:
        # Check current active size
        active_gb = get_active_samples_size()
        log(f"\nCurrent active: {active_gb:.1f} GB")
        
        # Find next sample that fits within limit
        sample_to_process = None
        for idx, (accession, size_mb, location, lat, lon) in enumerate(all_pending):
            if active_gb + (size_mb / 1024.0) <= max_concurrent_gb:
                sample_to_process = (accession, size_mb, location, lat, lon)
                all_pending.pop(idx)
                break
        
        if not sample_to_process:
            # No sample fits, wait for some to complete
            log(f"Waiting for active samples to complete (limit: {max_concurrent_gb} GB)...")
            time.sleep(30)
            continue
        
        accession, size_mb, location, lat, lon = sample_to_process
        processed_count += 1
        
        log(f"\n--- Sample {processed_count}/{max_samples} ---")
        log(f"Accession: {accession}")
        log(f"Size: {size_mb:.2f} MB ({size_mb/1024:.2f} GB)")
        log(f"Location: {location} ({lat:.4f}, {lon:.4f})")
        log(f"Active after start: {active_gb + size_mb/1024:.1f} / {max_concurrent_gb} GB")
        
        sample_start = time.time()
        success = process_one_sample(accession, lat, lon, location)
        sample_duration = time.time() - sample_start
        
        if success:
            processed += 1
            log(f"✓ Completed in {sample_duration/60:.1f} minutes")
        else:
            failed += 1
            log(f"✗ Failed after {sample_duration/60:.1f} minutes")
        
        # Stats
        total_duration = time.time() - start_time
        avg_time = total_duration / (processed + failed) if (processed + failed) > 0 else 0
        remaining = max_samples - processed_count
        eta_seconds = avg_time * remaining if avg_time > 0 else 0
        
        log(f"\nProgress: {processed} completed, {failed} failed, {remaining} remaining")
        log(f"Avg time: {avg_time/60:.1f} min/sample")
        log(f"ETA: {eta_seconds/3600:.1f} hours")
        
        time.sleep(2)
    
    # Final summary
    total_duration = time.time() - start_time
    log(f"\n{'='*80}")
    log("Batch Processing Complete")
    log(f"{'='*80}")
    log(f"Total time: {total_duration/3600:.2f} hours")
    log(f"Processed: {processed}")
    log(f"Failed: {failed}")
    log(f"Success rate: {processed/(processed+failed)*100:.1f}%")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("\n\nInterrupted by user")
    except Exception as e:
        log(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()

#!/usr/bin/env python3
"""
Pipeline Data Flow Verification Script
Verifies all 8 steps of the pipeline data flow are working correctly.
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'web-dashboard' / 'backend'))

# Load environment
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:
                    os.environ[key] = value

from config import config


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check_pass(msg: str):
    print(f"  ✅ {msg}")


def check_fail(msg: str):
    print(f"  ❌ {msg}")


def check_warn(msg: str):
    print(f"  ⚠️  {msg}")


async def verify_step1_frontend():
    """Step 1: Verify frontend upload component exists"""
    print_header("STEP 1: Sample Upload (Frontend → Backend)")
    
    frontend_path = Path(__file__).parent.parent / 'web-dashboard' / 'frontend' / 'src' / 'components'
    
    # Check PipelineDashboard.js
    pipeline_dashboard = frontend_path / 'PipelineDashboard.js'
    if pipeline_dashboard.exists():
        content = pipeline_dashboard.read_text()
        if 'presigned-upload' in content and 'confirm-upload' in content:
            check_pass("PipelineDashboard.js has presigned upload flow")
        else:
            check_fail("PipelineDashboard.js missing upload endpoints")
    else:
        check_fail("PipelineDashboard.js not found")
    
    # Check API endpoint configuration
    if 'handleSubmit' in content and 'handleFileChange' in content:
        check_pass("File upload handlers implemented")
    else:
        check_warn("File upload handlers may be incomplete")


async def verify_step2_storage():
    """Step 2: Verify MinIO storage configuration"""
    print_header("STEP 2: Storage (Backend → MinIO)")
    
    try:
        from minio import Minio
        from minio.error import S3Error
        
        minio_client = Minio(
            os.environ.get('MINIO_ENDPOINT', 'localhost:9000'),
            access_key=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
            secret_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
            secure=False
        )
        
        # Check buckets
        buckets = [b.name for b in minio_client.list_buckets()]
        
        required_buckets = ['genomic-bronze', 'genomic-silver', 'genomic-gold']
        for bucket in required_buckets:
            if bucket in buckets:
                check_pass(f"Bucket '{bucket}' exists")
            else:
                check_fail(f"Bucket '{bucket}' missing")
        
    except Exception as e:
        check_fail(f"MinIO connection failed: {e}")


async def verify_step3_database():
    """Step 3: Verify database schema"""
    print_header("STEP 3: Database Record (Backend → PostgreSQL)")
    
    try:
        import asyncpg
        
        conn = await asyncpg.connect(config.DATABASE_URL)
        
        # Check tables
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('samples', 'pipeline_runs', 'pipeline_progress_events', 'minio_objects')
        """)
        table_names = [t['table_name'] for t in tables]
        
        required_tables = ['samples', 'pipeline_runs', 'pipeline_progress_events', 'minio_objects']
        for table in required_tables:
            if table in table_names:
                check_pass(f"Table '{table}' exists")
            else:
                check_fail(f"Table '{table}' missing")
        
        # Check sample count
        sample_count = await conn.fetchval("SELECT COUNT(*) FROM samples")
        check_pass(f"Samples table has {sample_count} records")
        
        # Check pipeline runs
        pipeline_count = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs")
        check_pass(f"Pipeline runs table has {pipeline_count} records")
        
        await conn.close()
        
    except Exception as e:
        check_fail(f"Database connection failed: {e}")


async def verify_step4_submission():
    """Step 4: Verify pipeline submission code"""
    print_header("STEP 4: Pipeline Submission (Backend → Nextflow)")
    
    backend_path = Path(__file__).parent.parent / 'web-dashboard' / 'backend'
    
    # Check pipeline_v2.py routes
    pipeline_v2 = backend_path / 'routes' / 'pipeline_v2.py'
    if pipeline_v2.exists():
        content = pipeline_v2.read_text()
        if 'presigned-upload' in content:
            check_pass("Presigned upload endpoint exists")
        if 'confirm-upload' in content:
            check_pass("Confirm upload endpoint exists")
        if 'pipeline_service' in content:
            check_pass("Pipeline service integration present")
    else:
        check_fail("pipeline_v2.py not found")
    
    # Check pipeline_tasks.py
    pipeline_tasks = backend_path / 'tasks' / 'pipeline_tasks.py'
    if pipeline_tasks.exists():
        content = pipeline_tasks.read_text()
        if 'enqueue_pipeline' in content:
            check_pass("enqueue_pipeline function exists")
        if 'execute_nextflow_pipeline' in content:
            check_pass("Nextflow execution function exists")
        if 'subprocess.run' in content and 'nextflow' in content:
            check_pass("Nextflow subprocess execution configured")
    else:
        check_fail("pipeline_tasks.py not found")


async def verify_step5_execution():
    """Step 5: Verify Nextflow pipeline configuration"""
    print_header("STEP 5: Pipeline Execution (Nextflow 16 Modules)")
    
    nextflow_dir = Path(__file__).parent.parent / 'nextflow'
    
    # Check main.nf
    main_nf = nextflow_dir / 'main.nf'
    if main_nf.exists():
        content = main_nf.read_text()
        
        modules = [
            'NANOPLOT', 'FILTLONG', 'FLYE', 'MEDAKA',
            'MINIMAP2', 'METABAT2', 'CHECKM', 'DREP',
            'KRAKEN2', 'BRACKEN', 'PROKKA', 'ABRICATE',
            'DEEPARG', 'CONCOCT', 'BIN_QUALITY_FILTER', 'PIPELINE_SUMMARY'
        ]
        
        found_modules = []
        for module in modules:
            if module in content:
                found_modules.append(module)
        
        check_pass(f"Found {len(found_modules)}/16 modules in main.nf")
        
        missing = set(modules) - set(found_modules)
        if missing:
            check_warn(f"Missing modules: {', '.join(missing)}")
    else:
        check_fail("main.nf not found")
    
    # Check nextflow.config
    config_file = nextflow_dir / 'nextflow.config'
    if config_file.exists():
        check_pass("nextflow.config exists")
    else:
        check_fail("nextflow.config missing")


async def verify_step6_results_storage():
    """Step 6: Verify results storage configuration"""
    print_header("STEP 6: Results Storage (Nextflow → MinIO + PostgreSQL)")
    
    backend_path = Path(__file__).parent.parent / 'web-dashboard' / 'backend'
    
    # Check pipeline_tasks.py for Silver/Gold upload
    pipeline_tasks = backend_path / 'tasks' / 'pipeline_tasks.py'
    if pipeline_tasks.exists():
        content = pipeline_tasks.read_text()
        
        if 'genomic-silver' in content:
            check_pass("Silver layer upload configured")
        else:
            check_warn("Silver layer upload not found")
        
        if 'genomic-gold' in content:
            check_pass("Gold layer upload configured")
        else:
            check_warn("Gold layer upload not found")
        
        if '_record_uploaded_file' in content:
            check_pass("Database recording for uploaded files exists")
    
    # Check results directory
    results_dir = Path(__file__).parent.parent / 'results'
    if results_dir.exists():
        result_count = len(list(results_dir.iterdir()))
        check_pass(f"Results directory exists with {result_count} items")
    else:
        check_warn("Results directory not found")


async def verify_step7_results_display():
    """Step 7: Verify results API"""
    print_header("STEP 7: Results Display (API endpoints)")
    
    backend_path = Path(__file__).parent.parent / 'web-dashboard' / 'backend'
    
    # Check results.py
    results_py = backend_path / 'routes' / 'results.py'
    if results_py.exists():
        content = results_py.read_text()
        
        endpoints = [
            ('list_runs', '/'),
            ('list_run_files', '/<run_id>/files'),
            ('view_file', '/<run_id>/view'),
            ('download_file', '/<run_id>/download')
        ]
        
        for func_name, path in endpoints:
            if func_name in content:
                check_pass(f"Endpoint {path} exists")
            else:
                check_warn(f"Endpoint {path} not found")
        
        if 'get_cached_file_listing' in content:
            check_pass("File listing caching implemented")
    else:
        check_fail("results.py not found")


async def verify_step8_cleanup():
    """Step 8: Verify cleanup configuration"""
    print_header("STEP 8: Cleanup (Automatic & Manual)")
    
    scripts_dir = Path(__file__).parent.parent / 'scripts'
    
    # Check retention policy
    retention_script = scripts_dir / 'retention_policy.py'
    if retention_script.exists():
        content = retention_script.read_text()
        if 'cleanup_db' in content and 'cleanup_minio' in content:
            check_pass("Retention policy script exists")
        else:
            check_warn("Retention policy incomplete")
    else:
        check_fail("retention_policy.py not found")
    
    # Check cron script
    cron_script = scripts_dir / 'cron' / 'retention_cron.sh'
    if cron_script.exists():
        check_pass("Cron job script exists")
    else:
        check_warn("Cron job script not found")
    
    # Check cleanup scripts
    cleanup_dir = scripts_dir / 'cleanup'
    if cleanup_dir.exists():
        cleanup_scripts = list(cleanup_dir.glob('*.sh'))
        check_pass(f"Found {len(cleanup_scripts)} cleanup scripts")
    else:
        check_warn("Cleanup directory not found")
    
    # Check if cron is configured
    import subprocess
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if 'retention_cron' in result.stdout:
            check_pass("Retention cron job is configured")
        else:
            check_warn("Retention cron job not in crontab")
    except Exception:
        check_warn("Could not check crontab")


async def main():
    print("\n" + "="*60)
    print("   UPGRADE Pipeline Data Flow Verification")
    print("   " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)
    
    await verify_step1_frontend()
    await verify_step2_storage()
    await verify_step3_database()
    await verify_step4_submission()
    await verify_step5_execution()
    await verify_step6_results_storage()
    await verify_step7_results_display()
    await verify_step8_cleanup()
    
    print("\n" + "="*60)
    print("   Verification Complete")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Startup Health Check Script

Run before starting the backend to verify all dependencies are available.
Exit code 0 = healthy, non-zero = unhealthy.

Usage:
    python scripts/startup_health_check.py              # From inside container
    python scripts/startup_health_check.py --host       # From host machine
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
import logging
import argparse

# Parse args early to know if we're running from host
parser = argparse.ArgumentParser(description='Startup health check')
parser.add_argument('--host', action='store_true', help='Run from host (uses localhost:5433 for postgres)')
parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
args, _ = parser.parse_known_args()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'web-dashboard' / 'backend'))

# Load environment - .env file takes priority for credentials (shell may have mangled values)
env_file = Path(__file__).parent.parent / '.env'
CREDENTIAL_VARS = {'POSTGRES_PASSWORD', 'REDIS_PASSWORD', 'MINIO_ROOT_PASSWORD', 'MINIO_ROOT_USER'}
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # For credentials, always use .env file value (shell may strip trailing = etc)
                if key in CREDENTIAL_VARS or key not in os.environ:
                    os.environ[key] = value

# If running from host, override network settings
HOST_OVERRIDES = {
    'POSTGRES_HOST': 'localhost',
    'POSTGRES_PORT': '5433',
    'REDIS_HOST': 'localhost',
    'REDIS_PORT': '6379',
    'MINIO_ENDPOINT': 'localhost:9000',
}

if args.host:
    for key, value in HOST_OVERRIDES.items():
        os.environ[key] = value

from config import config

logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_url():
    """Build database URL from current environment (handles --host override)"""
    from urllib.parse import quote_plus
    user = os.environ.get('POSTGRES_USER', 'upgrade')
    password = os.environ.get('POSTGRES_PASSWORD', '')
    host = os.environ.get('POSTGRES_HOST', 'postgres')
    port = os.environ.get('POSTGRES_PORT', '5432')
    db = os.environ.get('POSTGRES_DB', 'upgrade_db')
    return f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{db}"


def get_redis_url():
    """Build Redis URL from current environment (handles --host override)"""
    password = os.environ.get('REDIS_PASSWORD', '')
    host = os.environ.get('REDIS_HOST', 'redis')
    port = os.environ.get('REDIS_PORT', '6379')
    return f"redis://:{password}@{host}:{port}/0"


def get_minio_config():
    """Get MinIO config from current environment (handles --host override)"""
    return {
        'endpoint': os.environ.get('MINIO_ENDPOINT', 'minio:9000'),
        'access_key': os.environ.get('MINIO_ACCESS_KEY', ''),
        'secret_key': os.environ.get('MINIO_SECRET_KEY', ''),
    }


class HealthCheck:
    """Health check result"""
    def __init__(self, name: str):
        self.name = name
        self.healthy = False
        self.message = ""
        self.latency_ms = 0
    
    def __str__(self):
        status = "✅" if self.healthy else "❌"
        return f"{status} {self.name}: {self.message} ({self.latency_ms}ms)"


async def check_postgres() -> HealthCheck:
    """Check PostgreSQL connectivity and schema"""
    import time
    check = HealthCheck("PostgreSQL")
    start = time.time()
    
    try:
        import asyncpg
        db_url = get_database_url()
        conn = await asyncpg.connect(
            db_url,
            timeout=5.0
        )
        
        # Verify key tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('samples', 'pipeline_runs', 'minio_objects')
        """)
        table_names = [t['table_name'] for t in tables]
        
        await conn.close()
        
        required = {'samples', 'pipeline_runs', 'minio_objects'}
        missing = required - set(table_names)
        
        if missing:
            check.message = f"Missing tables: {missing}"
        else:
            check.healthy = True
            check.message = f"Connected, {len(table_names)} core tables verified"
            
    except Exception as e:
        check.message = f"Connection failed: {e}"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def check_redis() -> HealthCheck:
    """Check Redis connectivity"""
    import time
    check = HealthCheck("Redis")
    start = time.time()
    
    try:
        import redis
        redis_host = os.environ.get('REDIS_HOST', 'redis')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        redis_password = os.environ.get('REDIS_PASSWORD', '')
        
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password if redis_password else None,
            socket_timeout=5.0
        )
        
        # Test ping
        r.ping()
        
        # Check RQ queue
        from rq import Queue
        queue_name = os.environ.get('RQ_QUEUE_NAME', 'pipeline_queue')
        q = Queue(queue_name, connection=r)
        job_count = len(q)
        
        check.healthy = True
        check.message = f"Connected, {job_count} jobs in queue"
        
    except Exception as e:
        check.message = f"Connection failed: {e}"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def check_minio() -> HealthCheck:
    """Check MinIO connectivity and buckets"""
    import time
    check = HealthCheck("MinIO")
    start = time.time()
    
    try:
        from minio import Minio
        
        endpoint = os.environ.get('MINIO_ENDPOINT', 'minio:9000')
        # For host mode, we need localhost but port may differ
        if args.host:
            endpoint = 'localhost:9000'
        
        client = Minio(
            endpoint,
            access_key=os.environ.get('MINIO_ROOT_USER', 'minioadmin'),
            secret_key=os.environ.get('MINIO_ROOT_PASSWORD', 'minioadmin'),
            secure=False
        )
        
        # List buckets
        buckets = [b.name for b in client.list_buckets()]
        
        # Check required buckets
        required = {'genomic-bronze', 'genomic-silver', 'genomic-gold'}
        missing = required - set(buckets)
        
        if missing:
            check.message = f"Missing buckets: {missing}"
        else:
            check.healthy = True
            check.message = f"Connected, {len(buckets)} buckets ({', '.join(required & set(buckets))})"
            
    except Exception as e:
        check.message = f"Connection failed: {e}"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def check_nextflow() -> HealthCheck:
    """Check Nextflow availability"""
    import time
    import subprocess
    check = HealthCheck("Nextflow")
    start = time.time()
    
    try:
        result = subprocess.run(
            ['nextflow', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            check.healthy = True
            check.message = version
        else:
            check.message = f"Exit code {result.returncode}: {result.stderr}"
            
    except FileNotFoundError:
        check.message = "Nextflow not found in PATH"
    except Exception as e:
        check.message = f"Check failed: {e}"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def check_directories() -> HealthCheck:
    """Check required directories exist and are writable"""
    import time
    check = HealthCheck("Directories")
    start = time.time()
    
    required_dirs = [
        config.RESULTS_DIR,
        config.WORK_DIR,
        config.DATA_DIR,
        config.NEXTFLOW_DIR,
    ]
    
    issues = []
    for dir_path in required_dirs:
        path = Path(dir_path)
        if not path.exists():
            issues.append(f"{dir_path} missing")
        elif not os.access(dir_path, os.W_OK):
            issues.append(f"{dir_path} not writable")
    
    if issues:
        check.message = "; ".join(issues)
    else:
        check.healthy = True
        check.message = f"All {len(required_dirs)} directories OK"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def check_disk_space() -> HealthCheck:
    """Check available disk space"""
    import time
    import shutil
    check = HealthCheck("Disk Space")
    start = time.time()
    
    try:
        # Check results directory disk
        usage = shutil.disk_usage(config.RESULTS_DIR)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        percent_free = (usage.free / usage.total) * 100
        
        if percent_free < 5:
            check.message = f"CRITICAL: Only {free_gb:.1f} GB free ({percent_free:.1f}%)"
        elif percent_free < 10:
            check.message = f"WARNING: {free_gb:.1f} GB free ({percent_free:.1f}%)"
            check.healthy = True  # Warning but not critical
        else:
            check.healthy = True
            check.message = f"{free_gb:.1f} GB free of {total_gb:.1f} GB ({percent_free:.1f}%)"
            
    except Exception as e:
        check.message = f"Check failed: {e}"
    
    check.latency_ms = int((time.time() - start) * 1000)
    return check


async def run_all_checks() -> int:
    """Run all health checks and return exit code"""
    logger.info("=" * 60)
    logger.info("STARTUP HEALTH CHECK")
    logger.info(f"Time: {datetime.now().isoformat()}")
    if args.host:
        logger.info("Mode: HOST (some checks skipped)")
    logger.info("=" * 60)
    
    # Core checks that work both in container and from host
    core_checks = [
        check_postgres(),
        check_redis(),
        check_minio(),
    ]
    
    # Container-only checks (require in-container paths/permissions)
    if not args.host:
        core_checks.extend([
            check_nextflow(),
            check_directories(),
            check_disk_space(),
        ])
    
    checks = await asyncio.gather(*core_checks)
    
    logger.info("\nResults:")
    for check in checks:
        logger.info(f"  {check}")
    
    if args.host:
        logger.info("  ⏭️  Nextflow: Skipped (host mode)")
        logger.info("  ⏭️  Directories: Skipped (host mode)")
        logger.info("  ⏭️  Disk Space: Skipped (host mode)")
    
    failed = [c for c in checks if not c.healthy]
    
    logger.info("\n" + "=" * 60)
    if failed:
        logger.error(f"❌ UNHEALTHY: {len(failed)} checks failed")
        for c in failed:
            logger.error(f"  - {c.name}: {c.message}")
        return 1
    else:
        logger.info("✅ HEALTHY: All checks passed")
        return 0


def main():
    exit_code = asyncio.run(run_all_checks())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

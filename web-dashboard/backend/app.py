"""
Sanic API for UPGRADE - Urban Pathogen Genomic Surveillance Network
"""
from sanic import Sanic, response
from sanic_cors import CORS
from sanic.response import json
import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
import logging
from pathlib import Path

# Import configuration with secrets support
from config import config

# Rate limiting for security (P0 security fix)
from rate_limiter import init_rate_limiter

# Import pipeline routes (V2 only — V1 removed)
from routes.pipeline_v2 import pipeline_v2_bp
from routes.samples import samples_bp
from routes.results import results_bp
from routes.auth import auth_bp
from routes.pipeline_monitoring import monitoring_bp

# Import service container
from container import create_service_container
from minio_helper import get_minio_client

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

app = Sanic("upgrade_api")

# Configure CORS with environment-based origin restrictions
# Development: ALLOWED_ORIGINS='*' (default, accepts all)
# Production: ALLOWED_ORIGINS='https://yourdomain.com,https://app.yourdomain.com'
allowed_origins = config.ALLOWED_ORIGINS.split(',') if config.ALLOWED_ORIGINS != '*' else ['*']
CORS(app, origins=allowed_origins if allowed_origins != ['*'] else '*')

# Configure request size limits for large FASTQ uploads (500MB)
app.config.REQUEST_MAX_SIZE = 500 * 1024 * 1024  # 500MB
app.config.REQUEST_TIMEOUT = 300  # 5 minutes for large uploads

# Add CORS headers middleware
@app.middleware('response')
async def add_cors_headers(request, response):
    # Use configured allowed origins instead of wildcard
    origin = request.headers.get('Origin', '')
    
    if config.ALLOWED_ORIGINS == '*':
        # Development mode: allow all origins
        response.headers['Access-Control-Allow-Origin'] = '*'
    elif origin in allowed_origins:
        # Production mode: allow only whitelisted origins
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

@app.options('/<path:path>')
async def options_handler(request, path):
    return response.text('', status=204)

# Register blueprints
app.blueprint(auth_bp)
app.blueprint(pipeline_v2_bp)
app.blueprint(samples_bp)
app.blueprint(results_bp)
app.blueprint(monitoring_bp)

# Database configuration from config module
DB_CONFIG = {
    'host': config.POSTGRES_HOST,
    'port': config.POSTGRES_PORT,
    'database': config.POSTGRES_DB,
    'user': config.POSTGRES_USER,
    'password': config.POSTGRES_PASSWORD,
}


@app.listener('before_server_start')
async def setup_db(app, loop):
    """Initialize database connection pool and services."""
    
    # Initialize rate limiter (uses Redis if available, memory fallback)
    # Protects against DDoS and brute-force attacks
    init_rate_limiter(app)
    
    # Pool sized for 50+ users × 2-5 concurrent requests = 100-250 peak connections
    app.ctx.db_pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=10,    # Warm pool — always-ready connections
        max_size=100,   # Peak production load
        max_queries=50000,
        max_inactive_connection_lifetime=300.0,
        command_timeout=60.0
    )
    app.ctx.logger = logger
    
    # OPTIMIZED: Redis connection pool for caching
    # Reduces DB load by 75x for frequently accessed data
    try:
        import redis.asyncio as redis
        app.ctx.redis = await redis.from_url(
            config.REDIS_URL,
            encoding='utf-8',
            decode_responses=True,
            max_connections=50  # Connection pool
        )
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning(f"Redis not available, caching disabled: {e}")
        app.ctx.redis = None

    # Separate sync, binary Redis connection for RQ job-liveness checks in the
    # stale-pipeline watchdog. RQ's Job/registry API is synchronous and needs
    # decode_responses=False (binary pickle payloads) — the async caching client
    # above is unsuitable for this.
    try:
        from redis import Redis as SyncRedis
        app.ctx.rq_redis = SyncRedis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            decode_responses=False
        )
        app.ctx.rq_redis.ping()
        logger.info("RQ liveness-check Redis connection initialized")
    except Exception as e:
        logger.warning(f"RQ Redis connection not available, watchdog liveness check disabled: {e}")
        app.ctx.rq_redis = None
    
    # Initialize MinIO client
    minio_client = get_minio_client()
    
    # Initialize service container with DI
    app.ctx.services = create_service_container(app.ctx.db_pool, minio_client)
    
    logger.info("Database pool created")
    logger.info("Service container initialized")
    logger.info("Pipeline routes registered")


@app.listener('after_server_start')
async def start_background_tasks(app, loop):
    """Start periodic background tasks."""
    app.ctx.stale_cleanup_task = asyncio.ensure_future(cleanup_stale_pipelines(app))


@app.listener('before_server_stop')
async def stop_background_tasks(app, loop):
    """Cancel background tasks on shutdown."""
    if hasattr(app.ctx, 'stale_cleanup_task'):
        app.ctx.stale_cleanup_task.cancel()


def _is_rq_job_alive(rq_redis, job_id: str) -> bool:
    """
    Best-effort liveness check against RQ/Redis directly, instead of trusting
    pipeline_runs.updated_at (which track_progress() writes to a separate
    pipeline_progress_events table and never touches — so a legitimately
    running multi-hour Nextflow stage looks identical in this column to a
    genuinely dead worker).

    Returns True if RQ still has a live record of the job (don't cancel),
    False if RQ has no such job or considers it finished/failed (safe to
    treat as dead).
    """
    if not rq_redis or not job_id:
        return False
    try:
        from rq.job import Job, JobStatus
        job = Job.fetch(job_id, connection=rq_redis)
        return job.get_status(refresh=True) in (
            JobStatus.STARTED, JobStatus.QUEUED, JobStatus.DEFERRED, JobStatus.SCHEDULED
        )
    except Exception:
        # NoSuchJobError or any lookup failure: RQ has no record, treat as not alive
        return False


async def cleanup_stale_pipelines(app):
    """Cancel pipelines stuck in 'queued' or 'running' status."""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        try:
            async with app.ctx.db_pool.acquire() as conn:
                # Queued with no job_id for >30 min: upload never completed
                queued = await conn.fetch("""
                    UPDATE pipeline_runs
                    SET status = 'failed',
                        error_message = 'Auto-cancelled: upload never completed (stale >30 min)',
                        completed_at = CURRENT_TIMESTAMP
                    WHERE status = 'queued'
                      AND job_id IS NULL
                      AND created_at < NOW() - INTERVAL '30 minutes'
                    RETURNING pipeline_id
                """)
                if queued:
                    ids = [r['pipeline_id'] for r in queued]
                    logger.warning(f"Auto-cancelled {len(queued)} stale queued pipelines: {ids}")

                # Running with no DB update for >48 hours: candidates only.
                # Real legitimate runs are documented at 2-32h, and updated_at
                # doesn't move during a long Nextflow stage, so time alone is
                # not sufficient evidence of a dead worker — confirm against
                # RQ's own job state before cancelling anything.
                candidates = await conn.fetch("""
                    SELECT pipeline_id, job_id
                    FROM pipeline_runs
                    WHERE status = 'running'
                      AND updated_at < NOW() - INTERVAL '48 hours'
                """)

                dead_ids = []
                alive_ids = []
                for row in candidates:
                    is_alive = await asyncio.to_thread(
                        _is_rq_job_alive, app.ctx.rq_redis, row['job_id']
                    )
                    (alive_ids if is_alive else dead_ids).append(row['pipeline_id'])

                if alive_ids:
                    logger.info(
                        f"Watchdog: {len(alive_ids)} pipeline(s) past 48h with stale "
                        f"updated_at but RQ reports the job still alive, not cancelling: {alive_ids}"
                    )

                if dead_ids:
                    running = await conn.fetch("""
                        UPDATE pipeline_runs
                        SET status = 'failed',
                            error_message = 'Auto-cancelled: no progress for 48+ hours and RQ has no live job record (worker likely crashed)',
                            completed_at = CURRENT_TIMESTAMP
                        WHERE pipeline_id = ANY($1::int[])
                          AND status = 'running'
                        RETURNING pipeline_id
                    """, dead_ids)
                    if running:
                        ids = [r['pipeline_id'] for r in running]
                        logger.warning(f"Auto-cancelled {len(running)} stuck running pipelines: {ids}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Stale pipeline cleanup error: {e}")


@app.listener('after_server_stop')
async def close_db(app, loop):
    """Close database connection pool."""
    await app.ctx.db_pool.close()
    if app.ctx.redis:
        await app.ctx.redis.close()
        logger.info("Redis connection closed")
    if getattr(app.ctx, 'rq_redis', None):
        app.ctx.rq_redis.close()
        logger.info("RQ Redis connection closed")
    logger.info("Database pool closed")


# ==================== API ENDPOINTS ====================

@app.route("/api/health")
async def health(request):
    """Health check with real system stats for frontend status bar."""
    try:
        async with app.ctx.db_pool.acquire() as conn:
            samples_count = await conn.fetchval(
                "SELECT COUNT(*) FROM samples"
            ) or 0
            active_pipelines = await conn.fetchval(
                "SELECT COUNT(*) FROM pipeline_runs WHERE status IN ('queued', 'running', 'pending')"
            ) or 0
    except Exception:
        samples_count = 0
        active_pipelines = 0

    return json({
        "status": "healthy",
        "samples_count": samples_count,
        "active_pipelines": active_pipelines,
        "measurement_datetime": datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv('SANIC_PORT', 8000)),
        debug=os.getenv('DEBUG', 'false').lower() == 'true',
        auto_reload=os.getenv('AUTO_RELOAD', 'false').lower() == 'true'
    )
"""
Database Connection Pool Manager
Provides asyncpg connection pooling for optimal performance
"""

import asyncpg
import logging
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Singleton database connection pool manager

    Benefits:
    - Reuses connections (500ms-2s saved per operation)
    - Automatic connection health checks
    - Graceful connection recycling
    - Query timeout protection
    """

    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def initialize(cls, min_size: int = 5, max_size: int = 20):
        """
        Initialize connection pool

        Args:
            min_size: Minimum number of connections to maintain
            max_size: Maximum number of connections allowed

        Pool sizing guidelines:
        - min_size: Warm pool, always ready
        - max_size: Handle peak load (1 connection per concurrent request)

        Example:
            - 5 concurrent requests → min_size=5 sufficient
            - 20 peak requests → max_size=20 needed
        """
        if cls._pool is not None:
            logger.warning("Connection pool already initialized")
            return cls._pool

        try:
            logger.info(f"Initializing database connection pool (min={min_size}, max={max_size})")

            cls._pool = await asyncpg.create_pool(
                config.DATABASE_URL,
                min_size=min_size,
                max_size=max_size,

                # Timeouts
                command_timeout=60.0,  # 60 second timeout on all queries
                timeout=30.0,  # 30 seconds to acquire connection from pool

                # Connection lifecycle
                max_queries=50000,  # Recycle connection after 50K queries
                max_inactive_connection_lifetime=300.0,  # Close idle connections after 5 min

                # Performance
                server_settings={
                    'application_name': 'genomic_pipeline_backend',
                    'jit': 'off'  # Disable JIT for simple queries (faster)
                }
            )

            # Test connection
            async with cls._pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')
                logger.info(f"✓ Connection pool initialized successfully")
                logger.info(f"  PostgreSQL: {version.split(',')[0]}")
                logger.info(f"  Pool size: {min_size}-{max_size} connections")

            return cls._pool

        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    @classmethod
    async def close(cls):
        """Close connection pool gracefully"""
        if cls._pool is not None:
            logger.info("Closing database connection pool...")
            await cls._pool.close()
            cls._pool = None
            logger.info("✓ Connection pool closed")

    @classmethod
    def get_pool(cls) -> asyncpg.Pool:
        """
        Get connection pool instance

        Raises:
            RuntimeError: If pool not initialized
        """
        if cls._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. "
                "Call DatabasePool.initialize() first"
            )
        return cls._pool

    @classmethod
    async def get_pool_stats(cls) -> dict:
        """Get connection pool statistics"""
        if cls._pool is None:
            return {'status': 'not_initialized'}

        return {
            'status': 'active',
            'size': cls._pool.get_size(),
            'free_size': cls._pool.get_idle_size(),
            'min_size': cls._pool.get_min_size(),
            'max_size': cls._pool.get_max_size()
        }


# Convenience functions for common patterns

async def execute_with_timeout(conn, query: str, *args, timeout: float = 10.0):
    """
    Execute query with timeout protection

    Args:
        conn: Database connection
        query: SQL query
        *args: Query parameters
        timeout: Timeout in seconds

    Raises:
        asyncio.TimeoutError: If query exceeds timeout
    """
    import asyncio

    try:
        return await asyncio.wait_for(
            conn.execute(query, *args),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Query timeout ({timeout}s): {query[:100]}...")
        raise


async def fetch_with_timeout(conn, query: str, *args, timeout: float = 10.0):
    """
    Fetch query results with timeout protection

    Args:
        conn: Database connection
        query: SQL query
        *args: Query parameters
        timeout: Timeout in seconds

    Raises:
        asyncio.TimeoutError: If query exceeds timeout
    """
    import asyncio

    try:
        return await asyncio.wait_for(
            conn.fetch(query, *args),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Query timeout ({timeout}s): {query[:100]}...")
        raise


# Usage examples
"""
Example 1: Initialize pool at application startup
----------------------------------------------------

from database import DatabasePool

# In app.py
@app.listener('before_server_start')
async def setup_db(app, loop):
    '''Initialize database connection pool'''
    app.ctx.db_pool = await DatabasePool.initialize(min_size=5, max_size=20)

@app.listener('after_server_stop')
async def teardown_db(app, loop):
    '''Close database connection pool'''
    await DatabasePool.close()


Example 2: Use pool in route handlers
--------------------------------------

from database import DatabasePool

@app.route('/api/pipeline/<pipeline_id>', methods=['GET'])
async def get_pipeline(request, pipeline_id):
    # Acquire connection from pool
    db_pool = DatabasePool.get_pool()

    async with db_pool.acquire() as conn:
        # Use connection
        pipeline = await conn.fetchrow('''
            SELECT * FROM pipeline_runs WHERE pipeline_id = $1
        ''', int(pipeline_id))

        if not pipeline:
            return response.json({'error': 'Pipeline not found'}, status=404)

        return response.json(dict(pipeline))


Example 3: Transaction with connection from pool
-------------------------------------------------

@app.route('/api/pipeline/create', methods=['POST'])
async def create_pipeline(request):
    db_pool = DatabasePool.get_pool()

    async with db_pool.acquire() as conn:
        # Start transaction
        async with conn.transaction():
            # Insert pipeline
            pipeline_id = await conn.fetchval('''
                INSERT INTO pipeline_runs (sample_id, status)
                VALUES ($1, $2)
                RETURNING pipeline_id
            ''', sample_id, 'pending')

            # Insert initial progress
            await conn.execute('''
                INSERT INTO pipeline_progress_events
                (pipeline_id, stage, status, percentage)
                VALUES ($1, $2, $3, $4)
            ''', pipeline_id, 'submitted', 'pending', 0)

            # Transaction auto-commits on success
            # Auto-rollback on exception

    return response.json({'pipeline_id': pipeline_id}, status=201)


Example 4: Query with timeout
------------------------------

from database import execute_with_timeout, fetch_with_timeout

async with db_pool.acquire() as conn:
    # Execute with 5 second timeout
    await execute_with_timeout(
        conn,
        '''UPDATE pipeline_runs SET status = $1 WHERE pipeline_id = $2''',
        'running', pipeline_id,
        timeout=5.0
    )

    # Fetch with 10 second timeout
    results = await fetch_with_timeout(
        conn,
        '''SELECT * FROM minio_objects WHERE pipeline_id = $1''',
        pipeline_id,
        timeout=10.0
    )


Example 5: Check pool stats (monitoring endpoint)
--------------------------------------------------

@app.route('/api/health/database', methods=['GET'])
async def database_health(request):
    stats = await DatabasePool.get_pool_stats()

    # Alert if pool is exhausted
    if stats['status'] == 'active' and stats['free_size'] == 0:
        logger.warning('Database connection pool exhausted!')

    return response.json({
        'database': stats,
        'healthy': stats['status'] == 'active' and stats['free_size'] > 0
    })
"""

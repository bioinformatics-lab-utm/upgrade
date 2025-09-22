# database/connection.py
import psycopg2
import logging
from config.settings import DATABASE_CONFIG

logger = logging.getLogger(__name__)

def create_db_connection():
    """Create database connection"""
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def test_db_connection():
    """Test database connection"""
    conn = create_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database test failed: {e}")
            return False
        finally:
            conn.close()
    return False

def get_db_stats():
    """Get database statistics"""
    conn = create_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            # Get table counts
            cur.execute("SELECT COUNT(*) FROM locations")
            location_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM pipeline_runs")
            pipeline_count = cur.fetchone()[0]
            
            # Get table sizes
            cur.execute("""
                SELECT tablename, 
                       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'public'
            """)
            table_sizes = cur.fetchall()
            
        return {
            'location_count': location_count,
            'pipeline_count': pipeline_count,
            'table_sizes': table_sizes
        }
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return None
    finally:
        conn.close()
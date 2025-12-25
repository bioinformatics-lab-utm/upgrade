#!/usr/bin/env python3
"""
Test script to verify Weather Consumer is working correctly.
Checks PostgreSQL connection pool and database state.
"""
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2
from psycopg2 import pool
from urllib.parse import quote_plus

def test_connection_pool():
    """Test PostgreSQL connection pooling."""
    logger.info("🔍 Testing PostgreSQL connection pool...")
    
    # Read password from secret
    postgres_password = os.getenv('POSTGRES_PASSWORD', '')
    if not postgres_password and os.path.exists('/run/secrets/postgres_password'):
        with open('/run/secrets/postgres_password', 'r') as f:
            postgres_password = f.read().strip()
    
    if not postgres_password:
        with open('secrets/postgres_password.txt', 'r') as f:
            postgres_password = f.read().strip()
    
    postgres_host = os.getenv('POSTGRES_HOST', 'localhost')
    postgres_port = os.getenv('POSTGRES_PORT', '5432')
    postgres_db = os.getenv('POSTGRES_DB', 'upgrade_db')
    postgres_user = os.getenv('POSTGRES_USER', 'upgrade')
    postgres_url = f'postgresql://{postgres_user}:{quote_plus(postgres_password)}@{postgres_host}:{postgres_port}/{postgres_db}'
    
    try:
        # Create connection pool
        db_pool = pool.SimpleConnectionPool(1, 5, postgres_url)
        logger.info("✅ Connection pool created successfully (1-5 connections)")
        
        # Test getting connection
        conn = db_pool.getconn()
        logger.info("✅ Got connection from pool")
        
        # Test query
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM weather_measurements")
            count = cur.fetchone()[0]
            logger.info(f"✅ Query successful: {count} weather measurements in database")
            
            # Test location lookup
            cur.execute("""
                SELECT location_id, location_name, city, country 
                FROM locations 
                WHERE is_active = true 
                LIMIT 5
            """)
            locations = cur.fetchall()
            logger.info(f"✅ Found {len(locations)} active locations:")
            for loc in locations:
                logger.info(f"   - {loc[1]} ({loc[2]}, {loc[3]}) - ID: {loc[0]}")
        
        # Return connection to pool
        db_pool.putconn(conn)
        logger.info("✅ Connection returned to pool")
        
        # Clean up
        db_pool.closeall()
        logger.info("✅ Pool closed successfully")
        
        logger.info("\n🎉 All tests passed! Weather Consumer should work correctly.")
        return True
        
    except Exception as e:
        logger.info(f"❌ Test failed: {e}")
        return False

def check_recent_data():
    """Check recent weather data."""
    logger.info("\n🔍 Checking recent weather data...")
    
    postgres_password = os.getenv('POSTGRES_PASSWORD', '')
    if not postgres_password and os.path.exists('secrets/postgres_password.txt'):
        with open('secrets/postgres_password.txt', 'r') as f:
            postgres_password = f.read().strip()
    
    postgres_host = os.getenv('POSTGRES_HOST', 'localhost')
    postgres_port = os.getenv('POSTGRES_PORT', '5432')
    postgres_db = os.getenv('POSTGRES_DB', 'upgrade_db')
    postgres_user = os.getenv('POSTGRES_USER', 'upgrade')
    postgres_url = f'postgresql://{postgres_user}:{quote_plus(postgres_password)}@{postgres_host}:{postgres_port}/{postgres_db}'
    
    try:
        conn = psycopg2.connect(postgres_url)
        with conn.cursor() as cur:
            # Check data from last 24 hours
            cur.execute("""
                SELECT 
                    DATE(measurement_datetime) as date,
                    COUNT(*) as count
                FROM weather_measurements
                WHERE measurement_datetime > NOW() - INTERVAL '7 days'
                GROUP BY DATE(measurement_datetime)
                ORDER BY date DESC
            """)
            results = cur.fetchall()
            
            if results:
                logger.info("📊 Weather measurements per day (last 7 days):")
                for date, count in results:
                    logger.info(f"   {date}: {count} measurements")
            else:
                logger.info("⚠️  No recent weather data found")
        
        conn.close()
        
    except Exception as e:
        logger.info(f"❌ Failed to check recent data: {e}")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Weather Consumer Test Script")
    logger.info("=" * 60)
    
    success = test_connection_pool()
    check_recent_data()
    
    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✅ Weather Consumer is ready to process messages!")
        sys.exit(0)
    else:
        logger.info("❌ Weather Consumer has issues, check logs above")
        sys.exit(1)

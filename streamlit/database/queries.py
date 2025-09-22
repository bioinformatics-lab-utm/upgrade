# database/queries.py
import streamlit as st
import pandas as pd
import warnings
from datetime import datetime
from database.connection import create_db_connection
import logging

logger = logging.getLogger(__name__)

@st.cache_data(ttl=300)
def fetch_locations():
    """Fetch locations from database"""
    conn = create_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT location_id, 
               COALESCE(city, 'Unknown') as city, 
               COALESCE(country, 'Unknown') as country, 
               COALESCE(location_name, city, 'Unknown') as location_name, 
               latitude, longitude, timezone, 
               COALESCE(campus_area, 'Unknown') as campus_area, 
               COALESCE(traffic_density, 'Unknown') as traffic_density, 
               COALESCE(indoor_outdoor, 'Unknown') as indoor_outdoor,
               created_at, is_active
        FROM locations 
        WHERE is_active = true
          AND latitude IS NOT NULL 
          AND longitude IS NOT NULL
        ORDER BY country, city, location_name
        """
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql(query, conn)
        
        return df
    except Exception as e:
        logger.error(f"Error fetching locations: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data(ttl=300)
def fetch_weather_data():
    """Fetch weather data from database"""
    conn = create_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        query = """
        SELECT w.weather_id, 
               w.measurement_datetime, 
               COALESCE(w.temperature, 0) as temperature, 
               COALESCE(w.humidity, 0) as humidity, 
               COALESCE(w.apparent_temperature, w.temperature, 0) as apparent_temperature, 
               COALESCE(w.rainfall, 0) as rainfall, 
               COALESCE(w.windspeed, 0) as windspeed, 
               COALESCE(w.wind_direction, 0) as wind_direction, 
               COALESCE(w.pressure_msl, 1013.25) as pressure_msl,
               COALESCE(w.surface_pressure, w.pressure_msl, 1013.25) as surface_pressure, 
               COALESCE(w.cloud_cover, 0) as cloud_cover, 
               COALESCE(w.uv_index, 0) as uv_index,
               COALESCE(w.weather_code, 0) as weather_code, 
               COALESCE(w.is_day, true) as is_day, 
               COALESCE(w.quality_score, 1.0) as quality_score,
               COALESCE(l.city, 'Unknown') as city, 
               COALESCE(l.country, 'Unknown') as country, 
               l.latitude, l.longitude,
               COALESCE(l.location_name, l.city, 'Unknown') as location_name
        FROM weather_measurements w
        JOIN locations l ON w.location_id = l.location_id
        WHERE w.measurement_datetime >= NOW() - INTERVAL '48 hours'
          AND l.latitude IS NOT NULL 
          AND l.longitude IS NOT NULL
        ORDER BY w.measurement_datetime DESC
        """
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql(query, conn)
        
        if not df.empty:
            df['measurement_datetime'] = pd.to_datetime(df['measurement_datetime'])
            if df['measurement_datetime'].dt.tz is not None:
                df['measurement_datetime'] = df['measurement_datetime'].dt.tz_localize(None)
            
            numeric_columns = ['temperature', 'humidity', 'windspeed', 'pressure_msl', 'cloud_cover', 'uv_index']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        return df
        
    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def get_pipeline_runs_from_db():
    """Get pipeline runs from PostgreSQL"""
    try:
        conn = create_db_connection()
        if not conn:
            return pd.DataFrame()
        
        query = """
        SELECT pipeline_id as run_id, 
               COALESCE(sample_id::varchar, 'unknown') as sample_id, 
               COALESCE(status, 'unknown') as status, 
               COALESCE(pipeline_name, 'unknown') as current_step,
               CASE 
                   WHEN status = 'completed' THEN 100
                   WHEN status = 'running' THEN 50
                   WHEN status = 'failed' THEN 0
                   ELSE 10
               END as progress_percentage,
               started_at as start_time, 
               completed_at as end_time, 
               runtime_minutes * 60 as duration_seconds,
               'Environmental' as sample_type,
               COALESCE(parameters, '') as description,
               COALESCE(results_path, log_file_path) as input_file_path, 
               error_message, 
               created_at
        FROM pipeline_runs 
        ORDER BY started_at DESC NULLS LAST, created_at DESC
        LIMIT 20
        """
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql(query, conn)
        
        conn.close()
        return df
        
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return pd.DataFrame()

def get_pipeline_runs_summary():
    """Get summary statistics for pipeline runs"""
    try:
        conn = create_db_connection()
        if not conn:
            return None
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('running', 'queued') THEN 1 ELSE 0 END) as running,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM pipeline_runs
            """)
            result = cur.fetchone()
            
        conn.close()
        
        return {
            'total': result[0],
            'running': result[1], 
            'completed': result[2],
            'failed': result[3]
        }
        
    except Exception as e:
        logger.error(f"Error getting pipeline summary: {e}")
        return None

def generate_pipeline_id():
    """Generate unique pipeline_id for new runs"""
    try:
        conn = create_db_connection()
        if not conn:
            return None
            
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(pipeline_id), 0) + 1 FROM pipeline_runs")
            next_id = cur.fetchone()[0]
        
        conn.close()
        return next_id
        
    except Exception as e:
        logger.error(f"Error generating pipeline_id: {e}")
        return None

def save_pipeline_run_to_db(run_data: dict):
    """Save pipeline run to database"""
    try:
        conn = create_db_connection()
        if not conn:
            return False
        
        with conn.cursor() as cur:
            # Check if record exists
            check_query = "SELECT COUNT(*) FROM pipeline_runs WHERE pipeline_id = %s"
            cur.execute(check_query, (run_data['run_id'],))
            exists = cur.fetchone()[0] > 0
            
            if exists:
                # Update existing record
                update_query = """
                UPDATE pipeline_runs SET
                    status = %s,
                    pipeline_name = %s,
                    error_message = %s,
                    started_at = CASE WHEN started_at IS NULL THEN %s ELSE started_at END,
                    completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE pipeline_id = %s
                """
                
                cur.execute(update_query, (
                    run_data['status'],
                    run_data.get('current_step', 'unknown'),
                    run_data.get('error_message'),
                    run_data['start_time'],
                    run_data['status'],
                    run_data['run_id']
                ))
            else:
                # Insert new record  
                insert_query = """
                INSERT INTO pipeline_runs 
                (pipeline_id, sample_id, pipeline_name, status, parameters, 
                 started_at, created_at, results_path, pipeline_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                # Get sample_id (simplified for now)
                sample_id_value = 1  # You can implement proper sample ID logic
                
                cur.execute(insert_query, (
                    run_data['run_id'],
                    sample_id_value,
                    run_data.get('current_step', 'streamlit_upload'),
                    run_data['status'],
                    run_data['description'],
                    run_data['start_time'],
                    datetime.now(),
                    run_data['input_file_path'],
                    '1.0'
                ))
            
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database save error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False
    

def create_sample_record(sample_data: dict):
    """Create sample record and return database ID"""
    try:
        conn = create_db_connection()
        if not conn:
            return None
            
        with conn.cursor() as cur:
            # Проверить по sample_code
            check_query = "SELECT sample_id FROM samples WHERE sample_code = %s"
            cur.execute(check_query, (sample_data['sample_id'],))
            existing = cur.fetchone()
            
            if existing:
                return existing[0]
            
            # Вставить новую запись
            insert_query = """
            INSERT INTO samples 
            (sample_code, sample_type, collection_date, location_id, 
             sequencing_platform, notes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING sample_id
            """
            
            cur.execute(insert_query, (
                sample_data['sample_id'],  # sample_code
                sample_data['sample_type'],
                datetime.now().date(),
                sample_data.get('location_id'),
                sample_data.get('sequencing_platform'),
                sample_data['description'],
                sample_data['created_at']
            ))
            
            sample_db_id = cur.fetchone()[0]
            conn.commit()
            return sample_db_id
            
    except Exception as e:
        logger.error(f"Error creating sample record: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()
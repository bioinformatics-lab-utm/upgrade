"""
Sanic API для UPGRADE - Urban Pathogen Genomic Surveillance Network
Combines weather data monitoring and genomic pipeline management
"""
from sanic import Sanic, response
from sanic_cors import CORS
from sanic.response import json
import asyncpg
import os
from datetime import datetime, timedelta
import logging
from pathlib import Path

# Import configuration with secrets support
from config import config

# Import pipeline routes
from routes.pipeline import pipeline_bp
from routes.samples import samples_bp
from routes.results import results_bp
from routes.auth import auth_bp
from routes.pipeline_monitoring import monitoring_bp

# Настройка логирования
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
app.blueprint(pipeline_bp)
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


# Пул соединений с БД
@app.listener('before_server_start')
async def setup_db(app, loop):
    """Инициализация пула соединений"""
    app.ctx.db_pool = await asyncpg.create_pool(**DB_CONFIG, min_size=5, max_size=20)
    app.ctx.logger = logger
    logger.info("Database pool created")
    logger.info("Pipeline routes registered")


@app.listener('after_server_stop')
async def close_db(app, loop):
    """Закрытие пула соединений"""
    await app.ctx.db_pool.close()
    logger.info("Database pool closed")


# ==================== API ENDPOINTS ====================

@app.route("/api/health")
async def health(request):
    """Проверка состояния API"""
    return json({"status": "healthy", "measurement_datetime": datetime.utcnow().isoformat()})


@app.route("/api/stations")
async def get_stations(request):
    """Получить список всех метеостанций с последними данными"""
    async with app.ctx.db_pool.acquire() as conn:
        query = """
            WITH latest_readings AS (
                SELECT DISTINCT ON (location_id)
                    location_id,
                    temperature,
                    humidity,
                    windspeed,
                    wind_direction,
                    rainfall,
                    measurement_datetime
                FROM weather_measurements
                ORDER BY location_id, measurement_datetime DESC
            )
            SELECT
                l.location_id as id,
                l.location_name as name,
                l.region,
                l.country,
                l.longitude,
                l.latitude,
                l.elevation,
                lr.temperature,
                lr.humidity,
                lr.windspeed as windspeed,
                lr.wind_direction,
                lr.rainfall as rainfall,
                lr.measurement_datetime as last_update
            FROM locations l
            LEFT JOIN latest_readings lr ON l.location_id = lr.location_id
            ORDER BY l.location_name
        """
        
        rows = await conn.fetch(query)
        
        stations = [
            {
                'id': row['id'],
                'name': row['name'],
                'region': row['region'],
                'country': row['country'],
                'longitude': float(row['longitude']) if row['longitude'] else None,
                'latitude': float(row['latitude']) if row['latitude'] else None,
                'elevation': float(row['elevation']) if row['elevation'] else None,
                'temperature': float(row['temperature']) if row['temperature'] else None,
                'humidity': float(row['humidity']) if row['humidity'] else None,
                'windspeed': float(row['windspeed']) if row['windspeed'] else None,
                'wind_direction': float(row['wind_direction']) if row['wind_direction'] else None,
                'rainfall': float(row['rainfall']) if row['rainfall'] else None,
                'last_update': row['last_update'].isoformat() if row['last_update'] else None
            }
            for row in rows
        ]
        
        return json({'stations': stations, 'count': len(stations)})


@app.route("/api/station/<location_id:int>/history")
async def get_station_history(request, location_id):
    """Получить историю погоды для локации"""
    hours = request.args.get('hours', 24)

    async with app.ctx.db_pool.acquire() as conn:
        query = """
            SELECT
                measurement_datetime as measurement_datetime,
                temperature,
                humidity,
                windspeed as windspeed,
                wind_direction,
                rainfall as rainfall,
                pressure_msl as pressure
            FROM weather_measurements
            WHERE location_id = $1
                AND measurement_datetime >= NOW() - INTERVAL '1 hour' * $2
            ORDER BY measurement_datetime DESC
            LIMIT 1000
        """
        
        rows = await conn.fetch(query, location_id, int(hours))
        
        history = [
            {
                'measurement_datetime': row['measurement_datetime'].isoformat(),
                'temperature': float(row['temperature']) if row['temperature'] else None,
                'humidity': float(row['humidity']) if row['humidity'] else None,
                'windspeed': float(row['windspeed']) if row['windspeed'] else None,
                'wind_direction': float(row['wind_direction']) if row['wind_direction'] else None,
                'rainfall': float(row['rainfall']) if row['rainfall'] else None,
                'pressure': float(row['pressure']) if row['pressure'] else None,
            }
            for row in rows
        ]
        
        return json({'location_id': location_id, 'history': history, 'count': len(history)})


@app.route("/api/stats")
async def get_stats(request):
    """Получить общую статистику"""
    async with app.ctx.db_pool.acquire() as conn:
        # Количество локаций
        locations_count = await conn.fetchval("SELECT COUNT(*) FROM locations WHERE is_active = true")

        # Количество измерений за последние 24 часа
        measurements_24h = await conn.fetchval("""
            SELECT COUNT(*) FROM weather_measurements
            WHERE measurement_datetime >= NOW() - INTERVAL '24 hours'
        """)

        # Средние значения по всем локациям
        avg_stats = await conn.fetchrow("""
            SELECT
                AVG(temperature) as avg_temp,
                AVG(humidity) as avg_humidity,
                AVG(windspeed) as avg_wind,
                AVG(rainfall) as avg_precip
            FROM weather_measurements
            WHERE measurement_datetime >= NOW() - INTERVAL '1 hour'
        """)

        # Экстремальные значения
        extremes = await conn.fetchrow("""
            SELECT
                MAX(temperature) as max_temp,
                MIN(temperature) as min_temp,
                MAX(windspeed) as max_wind
            FROM weather_measurements
            WHERE measurement_datetime >= NOW() - INTERVAL '24 hours'
        """)
        
        return json({
            'locations_count': locations_count,
            'measurements_24h': measurements_24h,
            'averages': {
                'temperature': float(avg_stats['avg_temp']) if avg_stats['avg_temp'] else None,
                'humidity': float(avg_stats['avg_humidity']) if avg_stats['avg_humidity'] else None,
                'windspeed': float(avg_stats['avg_wind']) if avg_stats['avg_wind'] else None,
                'rainfall': float(avg_stats['avg_precip']) if avg_stats['avg_precip'] else None,
            },
            'extremes': {
                'max_temperature': float(extremes['max_temp']) if extremes['max_temp'] else None,
                'min_temperature': float(extremes['min_temp']) if extremes['min_temp'] else None,
                'max_windspeed': float(extremes['max_wind']) if extremes['max_wind'] else None,
            }
        })


@app.route("/api/heatmap")
async def get_heatmap_data(request):
    """Получить данные для тепловой карты"""
    metric = request.args.get('metric', 'temperature')
    
    valid_metrics = ['temperature', 'humidity', 'windspeed', 'rainfall']
    if metric not in valid_metrics:
        return json({'error': 'Invalid metric'}, status=400)
    
    async with app.ctx.db_pool.acquire() as conn:
        query = f"""
            WITH latest_readings AS (
                SELECT DISTINCT ON (station_id)
                    location_id,
                    {metric} as value,
                    measurement_datetime
                FROM weather_measurements
                ORDER BY location_id, measurement_datetime DESC
            )
            SELECT 
                ST_X(s.location::geometry) as longitude,
                ST_Y(s.location::geometry) as latitude,
                lr.value,
                s.name
            FROM locations s
            INNER JOIN latest_readings lr ON s.id = lr.location_id
            WHERE lr.value IS NOT NULL
        """
        
        rows = await conn.fetch(query)
        
        points = [
            {
                'longitude': float(row['longitude']),
                'latitude': float(row['latitude']),
                'value': float(row['value']),
                'name': row['name']
            }
            for row in rows
        ]
        
        return json({'metric': metric, 'points': points, 'count': len(points)})


@app.route("/api/regions")
async def get_regions(request):
    """Получить статистику по регионам"""
    async with app.ctx.db_pool.acquire() as conn:
        query = """
            WITH latest_readings AS (
                SELECT DISTINCT ON (station_id)
                    location_id,
                    temperature,
                    humidity,
                    windspeed
                FROM weather_measurements
                ORDER BY location_id, measurement_datetime DESC
            )
            SELECT 
                s.region,
                COUNT(s.id) as station_count,
                AVG(lr.temperature) as avg_temp,
                AVG(lr.humidity) as avg_humidity,
                AVG(lr.windspeed) as avg_wind
            FROM locations s
            LEFT JOIN latest_readings lr ON s.id = lr.location_id
            GROUP BY s.region
            ORDER BY s.region
        """
        
        rows = await conn.fetch(query)
        
        regions = [
            {
                'region': row['region'],
                'station_count': row['station_count'],
                'avg_temperature': float(row['avg_temp']) if row['avg_temp'] else None,
                'avg_humidity': float(row['avg_humidity']) if row['avg_humidity'] else None,
                'avg_windspeed': float(row['avg_wind']) if row['avg_wind'] else None,
            }
            for row in rows
        ]
        
        return json({'regions': regions, 'count': len(regions)})


@app.route("/api/alerts")
async def get_alerts(request):
    """Получить предупреждения о критических погодных условиях"""
    async with app.ctx.db_pool.acquire() as conn:
        query = """
            WITH latest_readings AS (
                SELECT DISTINCT ON (station_id)
                    location_id,
                    temperature,
                    windspeed,
                    rainfall,
                    measurement_datetime
                FROM weather_measurements
                ORDER BY location_id, measurement_datetime DESC
            )
            SELECT 
                s.id,
                s.name,
                s.region,
                ST_X(s.location::geometry) as longitude,
                ST_Y(s.location::geometry) as latitude,
                lr.temperature,
                lr.windspeed,
                lr.rainfall,
                lr.measurement_datetime,
                CASE
                    WHEN lr.temperature > 35 THEN 'extreme_heat'
                    WHEN lr.temperature < -20 THEN 'extreme_cold'
                    WHEN lr.windspeed > 25 THEN 'strong_wind'
                    WHEN lr.rainfall > 50 THEN 'heavy_rain'
                    ELSE 'normal'
                END as alert_type
            FROM locations s
            INNER JOIN latest_readings lr ON s.id = lr.location_id
            WHERE lr.temperature > 35 
                OR lr.temperature < -20 
                OR lr.windspeed > 25 
                OR lr.rainfall > 50
            ORDER BY lr.measurement_datetime DESC
        """
        
        rows = await conn.fetch(query)
        
        alerts = [
            {
                'station_id': row['id'],
                'station_name': row['name'],
                'region': row['region'],
                'longitude': float(row['longitude']),
                'latitude': float(row['latitude']),
                'alert_type': row['alert_type'],
                'temperature': float(row['temperature']) if row['temperature'] else None,
                'windspeed': float(row['windspeed']) if row['windspeed'] else None,
                'rainfall': float(row['rainfall']) if row['rainfall'] else None,
                'measurement_datetime': row['measurement_datetime'].isoformat()
            }
            for row in rows
        ]
        
        return json({'alerts': alerts, 'count': len(alerts)})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv('SANIC_PORT', 8000)),
        debug=os.getenv('DEBUG', 'false').lower() == 'true',
        auto_reload=os.getenv('AUTO_RELOAD', 'false').lower() == 'true'
    )
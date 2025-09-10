from sanic import Sanic, response
from sanic_cors import CORS
import asyncpg
import os
import json
from datetime import datetime, date
from sanic.response import file
from sanic.exceptions import NotFound

app = Sanic("UPGRADE-API")
CORS(app)

# Database connection
DATABASE_URL = "postgresql://upgrade:upgrade123@localhost:5432/upgrade_db"

@app.before_server_start
async def setup_db(app, loop):
    """Установка соединения с базой данных"""
    try:
        app.ctx.db = await asyncpg.connect(DATABASE_URL)
        print("Database connected successfully")
    except Exception as e:
        print(f"Database connection failed: {e}")

@app.after_server_stop
async def close_db(app, loop):
    """Закрытие соединения с базой данных"""
    if hasattr(app.ctx, 'db'):
        await app.ctx.db.close()

# Custom JSON encoder for datetime objects
def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

# API маршруты
@app.route("/api/health")
async def health_check(request):
    """Проверка состояния API"""
    try:
        # Проверка подключения к базе
        await app.ctx.db.fetchval("SELECT 1")
        return response.json({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return response.json({
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, status=500)

@app.route("/api/locations")
async def get_locations(request):
    """Получить все локации"""
    try:
        query = """
        SELECT location_id, city, country, location_name, 
               latitude, longitude, timezone, campus_area, 
               traffic_density, indoor_outdoor, created_at
        FROM locations 
        WHERE is_active = true
        ORDER BY country, city
        """
        rows = await app.ctx.db.fetch(query)
        
        locations = []
        for row in rows:
            location = dict(row)
            locations.append(location)
        
        return response.json({
            "success": True,
            "count": len(locations),
            "data": locations
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

@app.route("/api/weather")
async def get_weather(request):
    """Получить погодные данные"""
    try:
        # Параметры запроса
        limit = int(request.args.get('limit', 100))
        city = request.args.get('city')
        country = request.args.get('country')
        
        # Базовый запрос
        query = """
        SELECT w.weather_id, w.measurement_datetime, w.temperature, 
               w.humidity, w.apparent_temperature, w.rainfall, 
               w.windspeed, w.wind_direction, w.pressure_msl,
               w.surface_pressure, w.cloud_cover, w.uv_index,
               w.weather_code, w.is_day, w.quality_score,
               w.data_quality, w.source,
               l.city, l.country, l.latitude, l.longitude, l.location_name
        FROM weather_measurements w
        JOIN locations l ON w.location_id = l.location_id
        WHERE 1=1
        """
        
        params = []
        param_count = 1
        
        # Фильтры
        if city:
            query += f" AND LOWER(l.city) = LOWER(${param_count})"
            params.append(city)
            param_count += 1
            
        if country:
            query += f" AND LOWER(l.country) = LOWER(${param_count})"
            params.append(country)
            param_count += 1
        
        query += f" ORDER BY w.measurement_datetime DESC LIMIT ${param_count}"
        params.append(limit)
        
        rows = await app.ctx.db.fetch(query, *params)
        
        weather_data = []
        for row in rows:
            data = dict(row)
            weather_data.append(data)
        
        return response.json({
            "success": True,
            "count": len(weather_data),
            "data": weather_data
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

@app.route("/api/weather/latest")
async def get_latest_weather(request):
    """Получить последние погодные данные для каждого города"""
    try:
        query = """
        WITH latest_weather AS (
            SELECT w.*, l.city, l.country, l.latitude, l.longitude, l.location_name,
                   ROW_NUMBER() OVER (PARTITION BY l.location_id ORDER BY w.measurement_datetime DESC) as rn
            FROM weather_measurements w
            JOIN locations l ON w.location_id = l.location_id
        )
        SELECT weather_id, measurement_datetime, temperature, humidity, 
               apparent_temperature, rainfall, windspeed, wind_direction, 
               pressure_msl, surface_pressure, cloud_cover, uv_index,
               weather_code, is_day, quality_score, data_quality, source,
               city, country, latitude, longitude, location_name
        FROM latest_weather 
        WHERE rn = 1
        ORDER BY city
        """
        
        rows = await app.ctx.db.fetch(query)
        
        weather_data = []
        for row in rows:
            data = dict(row)
            weather_data.append(data)
        
        return response.json({
            "success": True,
            "count": len(weather_data),
            "data": weather_data
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

@app.route("/api/weather/stats")
async def get_weather_stats(request):
    """Получить статистику погодных данных"""
    try:
        stats_query = """
        SELECT 
            COUNT(*) as total_measurements,
            COUNT(DISTINCT location_id) as locations_count,
            MAX(measurement_datetime) as last_measurement,
            MIN(measurement_datetime) as first_measurement,
            AVG(temperature) as avg_temperature,
            AVG(humidity) as avg_humidity,
            AVG(windspeed) as avg_windspeed
        FROM weather_measurements
        """
        
        recent_query = """
        SELECT 
            COUNT(*) as recent_measurements,
            AVG(temperature) as recent_avg_temp,
            AVG(humidity) as recent_avg_humidity
        FROM weather_measurements 
        WHERE measurement_datetime >= NOW() - INTERVAL '24 hours'
        """
        
        stats_row = await app.ctx.db.fetchrow(stats_query)
        recent_row = await app.ctx.db.fetchrow(recent_query)
        
        stats = dict(stats_row) if stats_row else {}
        recent = dict(recent_row) if recent_row else {}
        
        return response.json({
            "success": True,
            "data": {
                **stats,
                **recent
            }
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

@app.route("/api/weather/cities")
async def get_cities(request):
    """Получить список городов с погодными данными"""
    try:
        query = """
        SELECT DISTINCT l.city, l.country, COUNT(w.weather_id) as measurement_count,
               MAX(w.measurement_datetime) as last_update
        FROM locations l
        LEFT JOIN weather_measurements w ON l.location_id = w.location_id
        WHERE l.is_active = true
        GROUP BY l.city, l.country
        ORDER BY l.country, l.city
        """
        
        rows = await app.ctx.db.fetch(query)
        
        cities = []
        for row in rows:
            city_data = dict(row)
            cities.append(city_data)
        
        return response.json({
            "success": True,
            "count": len(cities),
            "data": cities
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

@app.route("/api/geojson/weather")
async def get_geojson_weather(request):
    """Получить погодные данные в формате GeoJSON"""
    try:
        query = """
        SELECT w.weather_id, w.measurement_datetime, w.temperature, 
               w.humidity, w.apparent_temperature, w.rainfall, 
               w.windspeed, w.wind_direction, w.pressure_msl,
               w.surface_pressure, w.cloud_cover, w.uv_index,
               w.weather_code, w.is_day, w.quality_score,
               w.data_quality, w.source,
               l.city, l.country, l.latitude, l.longitude, l.location_name
        FROM weather_measurements w
        JOIN locations l ON w.location_id = l.location_id
        WHERE w.measurement_datetime >= NOW() - INTERVAL '24 hours'
        ORDER BY w.measurement_datetime DESC
        """
        
        rows = await app.ctx.db.fetch(query)
        
        features = []
        for row in rows:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]]
                },
                "properties": dict(row)
            }
            features.append(feature)
        
        return response.json({
            "type": "FeatureCollection",
            "features": features
        })
    except Exception as e:
        return response.json({
            "success": False,
            "error": str(e)
        }, status=500)

# Статические файлы React - должны быть после API маршрутов
@app.route('/')
async def serve_index(request):
    return await file(os.path.join(os.path.dirname(__file__), '../frontend/build/index.html'))

@app.route('/<path:path>')
async def serve_static(request, path):
    # Пробуем отдать статический файл
    file_path = os.path.join(os.path.dirname(__file__), '../frontend/build', path)
    if os.path.exists(file_path):
        return await file(file_path)
    # Если файл не найден, отдаем index.html (для поддержки роутинга React)
    index_path = os.path.join(os.path.dirname(__file__), '../frontend/build/index.html')
    if os.path.exists(index_path):
        return await file(index_path)
    raise NotFound("File not found")

@app.exception(Exception)
async def handle_exception(request, exception):
    """Глобальная обработка исключений"""
    if isinstance(exception, asyncpg.PostgresError):
        return response.json({
            "success": False,
            "error": "Database error occurred"
        }, status=500)
    
    return response.json({
        "success": False,
        "error": str(exception)
    }, status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
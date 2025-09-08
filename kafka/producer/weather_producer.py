import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
import redis
import psycopg2
from kafka import KafkaProducer
import schedule

logging.basicConfig(level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')))
logger = logging.getLogger(__name__)

class WeatherProducer:
    def __init__(self):
        # Конфигурация
        self.kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092').split(',')
        self.open_meteo_url = os.getenv('OPEN_METEO_URL', 'https://api.open-meteo.com/v1/forecast')
        self.postgres_url = os.getenv('POSTGRES_URL', 'postgresql://upgrade:upgrade123@postgres:5432/upgrade_db')
        self.redis_password = os.getenv('REDIS_PASSWORD', '')
        self.collection_interval = int(os.getenv('COLLECTION_INTERVAL_MINUTES', '30'))
        self.max_cities_per_batch = int(os.getenv('MAX_CITIES_PER_BATCH', '50'))  # Ограничение для API
        
        # Kafka топики
        self.topic = 'weather-data'
        
        # Fallback города (если база недоступна)
        self.fallback_cities = [
            {'id': 'suceava', 'name': 'Suceava', 'lat': 47.6635, 'lon': 26.2535, 'county': 'Suceava', 'country': 'Romania'},
            {'id': 'bucharest', 'name': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025, 'county': 'Bucharest', 'country': 'Romania'},
            {'id': 'chisinau', 'name': 'Chisinau', 'lat': 47.0105, 'lon': 28.8638, 'county': 'Chisinau', 'country': 'Moldova'},
        ]
        
        # Инициализация компонентов
        self.cities = []
        self.producer = None
        self.redis_client = None
        self.session = None

    async def load_cities_from_database(self) -> List[Dict]:
        """Загрузить города из базы данных"""
        try:
            conn = psycopg2.connect(self.postgres_url)
            cur = conn.cursor()
            
            # Исправленный запрос без колонки county
            cur.execute("""
                SELECT 
                    location_name, 
                    latitude, 
                    longitude, 
                    COALESCE(region, city, 'Unknown') as county,
                    country,
                    LOWER(REPLACE(REPLACE(REPLACE(location_name, ' Weather Station', ''), ' ', '_'), '-', '_')) as city_id
                FROM locations 
                WHERE is_active = true 
                AND country IN ('Romania', 'Moldova')
                AND latitude IS NOT NULL 
                AND longitude IS NOT NULL
                ORDER BY 
                    CASE WHEN country = 'Romania' THEN 1 ELSE 2 END,
                    location_name
                LIMIT %s
            """, (self.max_cities_per_batch,))
            
            cities = []
            for row in cur.fetchall():
                city_data = {
                    'id': row[5],  # generated city_id
                    'name': row[0].replace(' Weather Station', ''),
                    'lat': float(row[1]),
                    'lon': float(row[2]),
                    'county': row[3],
                    'country': row[4]
                }
                cities.append(city_data)
            
            cur.close()
            conn.close()
            
            logger.info(f"Loaded {len(cities)} cities from database")
            return cities
            
        except Exception as e:
            logger.error(f"Failed to load cities from database: {e}")
            logger.warning("Using fallback cities list")
            return self.fallback_cities

    async def initialize(self):
        """Инициализация producer"""
        try:
            # Загрузить города из базы данных
            logger.info("Loading cities from database...")
            self.cities = await self.load_cities_from_database()
            
            if not self.cities:
                logger.warning("No cities loaded, using fallback list")
                self.cities = self.fallback_cities
            
            # Kafka Producer
            self.producer = KafkaProducer(
                bootstrap_servers=self.kafka_servers,
                value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
                key_serializer=lambda x: x.encode('utf-8'),
                acks='all',
                retries=3,
                retry_backoff_ms=1000,
                max_in_flight_requests_per_connection=5
            )
            
            # Redis для кэширования (опционально)
            if self.redis_password:
                self.redis_client = redis.Redis(
                    host='redis', 
                    port=6379, 
                    password=self.redis_password,
                    decode_responses=True
                )
                logger.info("Redis client initialized")
            
            # HTTP session с увеличенным timeout для большого количества городов
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            logger.info(f"Producer initialized successfully with {len(self.cities)} cities")
            
        except Exception as e:
            logger.error(f"Failed to initialize producer: {e}")
            raise

    async def fetch_weather_data(self, city: Dict) -> Dict:
        """Получить погодные данные для города из Open-Meteo API"""
        
        params = {
            'latitude': city['lat'],
            'longitude': city['lon'],
            'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,precipitation,wind_speed_10m,cloud_cover',
            'hourly': 'temperature_2m,precipitation,weather_code',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum',
            'timezone': 'auto',  # Автоматически определить часовой пояс
            'forecast_days': 1
        }
        
        try:
            async with self.session.get(self.open_meteo_url, params=params) as response:
                if response.status == 200:
                    api_data = await response.json()
                    
                    # Проверить качество данных
                    completeness = self._calculate_completeness(api_data)
                    
                    # Создать событие для Kafka
                    weather_event = {
                        'event_id': str(uuid.uuid4()),
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'source': 'open-meteo-api',
                        'location': {
                            'city_id': city['id'],
                            'name': city['name'],
                            'county': city['county'],
                            'country': city['country'],
                            'latitude': city['lat'],
                            'longitude': city['lon']
                        },
                        'weather_data': api_data,
                        'quality': {
                            'status': 'success' if completeness > 0.3 else 'partial',
                            'completeness': completeness,
                            'data_points': self._count_valid_data_points(api_data)
                        }
                    }
                    
                    logger.info(f"Successfully collected weather data for {city['name']} ({city['country']}) - completeness: {completeness:.2f}")
                    return weather_event
                    
                else:
                    logger.error(f"API error for {city['name']}: HTTP {response.status}")
                    return self._create_error_event(city, f"HTTP {response.status}")
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching data for {city['name']}")
            return self._create_error_event(city, "Timeout")
        except Exception as e:
            logger.error(f"Error fetching data for {city['name']}: {e}")
            return self._create_error_event(city, str(e))

    def _calculate_completeness(self, data: Dict) -> float:
        """Рассчитать полноту данных"""
        total_fields = 0
        valid_fields = 0
        
        # Проверить текущие данные
        if 'current' in data and isinstance(data['current'], dict):
            for key, value in data['current'].items():
                if key not in ['time', 'interval']:
                    total_fields += 1
                    if value is not None:
                        valid_fields += 1
        
        # Проверить часовые данные (первые несколько значений)
        if 'hourly' in data and isinstance(data['hourly'], dict):
            for key, values in data['hourly'].items():
                if key != 'time' and isinstance(values, list) and len(values) > 0:
                    total_fields += 1
                    if values[0] is not None:
                        valid_fields += 1
        
        return round(valid_fields / total_fields if total_fields > 0 else 0, 3)

    def _count_valid_data_points(self, data: Dict) -> int:
        """Подсчитать количество валидных точек данных"""
        count = 0
        
        if 'current' in data and isinstance(data['current'], dict):
            for key, value in data['current'].items():
                if key not in ['time', 'interval'] and value is not None:
                    count += 1
        
        return count

    def _create_error_event(self, city: Dict, error_message: str) -> Dict:
        """Создать событие об ошибке"""
        return {
            'event_id': str(uuid.uuid4()),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'open-meteo-api',
            'location': {
                'city_id': city['id'],
                'name': city['name'],
                'country': city['country'],
                'latitude': city['lat'],
                'longitude': city['lon']
            },
            'weather_data': None,
            'quality': {
                'status': 'error',
                'error_message': error_message,
                'completeness': 0.0,
                'data_points': 0
            }
        }

    async def send_to_kafka(self, weather_event: Dict):
        """Отправить данные в Kafka"""
        try:
            city_id = weather_event['location']['city_id']
            
            future = self.producer.send(
                topic=self.topic,
                key=city_id,
                value=weather_event
            )
            
            # Ждем подтверждения
            record_metadata = future.get(timeout=10)
            logger.debug(f"Sent data for {city_id} to partition {record_metadata.partition}")
            
        except Exception as e:
            logger.error(f"Failed to send to Kafka: {e}")
            raise

    async def collect_and_send_weather_data(self):
        """Собрать данные для всех городов и отправить в Kafka"""
        start_time = time.time()
        logger.info(f"Starting weather collection for {len(self.cities)} cities")
        
        successful = 0
        failed = 0
        partial = 0
        
        # Обработать города батчами для избежания перегрузки API
        batch_size = 10  # Количество одновременных запросов
        
        for i in range(0, len(self.cities), batch_size):
            batch = self.cities[i:i + batch_size]
            
            # Собрать данные для батча
            tasks = [self.fetch_weather_data(city) for city in batch]
            weather_events = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Отправить данные в Kafka
            for j, weather_event in enumerate(weather_events):
                if isinstance(weather_event, Exception):
                    logger.error(f"Exception for {batch[j]['name']}: {weather_event}")
                    failed += 1
                    continue
                
                try:
                    await self.send_to_kafka(weather_event)
                    
                    status = weather_event['quality']['status']
                    if status == 'success':
                        successful += 1
                    elif status == 'partial':
                        partial += 1
                    else:
                        failed += 1
                        
                except Exception as e:
                    logger.error(f"Failed to send {batch[j]['name']} to Kafka: {e}")
                    failed += 1
            
            # Пауза между батчами
            if i + batch_size < len(self.cities):
                await asyncio.sleep(2)
        
        # Убеждаемся что все сообщения отправлены
        self.producer.flush()
        
        duration = time.time() - start_time
        logger.info(f"Collection completed in {duration:.1f}s. Success: {successful}, Partial: {partial}, Failed: {failed}")
        
        # Сохранить статистику в Redis
        if self.redis_client:
            try:
                stats = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'successful': successful,
                    'partial': partial,
                    'failed': failed,
                    'total': len(self.cities),
                    'duration_seconds': round(duration, 1),
                    'cities_per_second': round(len(self.cities) / duration, 2)
                }
                self.redis_client.setex('weather:last_collection', 3600, json.dumps(stats))
                logger.info(f"Stats saved to Redis: {stats['cities_per_second']} cities/sec")
            except Exception as e:
                logger.warning(f"Failed to save stats to Redis: {e}")

    def run_collection(self):
        """Запустить сбор данных (для scheduler)"""
        try:
            asyncio.run(self.collect_and_send_weather_data())
        except Exception as e:
            logger.error(f"Collection failed: {e}")

    async def refresh_cities_list(self):
        """Обновить список городов из базы данных"""
        try:
            new_cities = await self.load_cities_from_database()
            if new_cities and len(new_cities) > 0:
                old_count = len(self.cities)
                self.cities = new_cities
                logger.info(f"Cities list refreshed: {old_count} -> {len(self.cities)}")
            else:
                logger.warning("Failed to refresh cities list, keeping current list")
        except Exception as e:
            logger.error(f"Error refreshing cities list: {e}")

    async def start_producer(self):
        """Запустить producer с расписанием"""
        logger.info("Starting Weather Producer for UPGRADE project")
        
        await self.initialize()
        
        # Настроить расписание
        schedule.every(self.collection_interval).minutes.do(self.run_collection)
        
        # Обновлять список городов каждые 6 часов
        schedule.every(6).hours.do(lambda: asyncio.create_task(self.refresh_cities_list()))
        
        # Запустить первый сбор
        logger.info("Running initial weather data collection...")
        await self.collect_and_send_weather_data()
        
        # Основной цикл
        logger.info(f"Producer started. Collecting data every {self.collection_interval} minutes.")
        
        running = True
        while running:
            try:
                schedule.run_pending()
                await asyncio.sleep(30)  # Проверка каждые 30 секунд
                
                # Heartbeat в Redis
                if self.redis_client:
                    try:
                        heartbeat = {
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'status': 'running',
                            'cities_count': len(self.cities),
                            'next_collection': schedule.jobs[0].next_run.isoformat() if schedule.jobs else None,
                            'api_endpoint': self.open_meteo_url
                        }
                        self.redis_client.setex('weather:producer_heartbeat', 120, json.dumps(heartbeat))
                    except Exception as e:
                        logger.warning(f"Failed to update heartbeat: {e}")
                        
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)

    async def cleanup(self):
        """Очистка ресурсов"""
        try:
            if self.session:
                await self.session.close()
            if self.producer:
                self.producer.close()
            if self.redis_client:
                self.redis_client.close()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

async def main():
    producer = WeatherProducer()
    try:
        await producer.start_producer()
    except Exception as e:
        logger.error(f"Producer failed: {e}")
    finally:
        await producer.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
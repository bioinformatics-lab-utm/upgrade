import json
import logging
import os
import time
from datetime import datetime, timezone
from io import BytesIO

import psycopg2
from psycopg2.extras import RealDictCursor
from kafka import KafkaConsumer
from minio import Minio
import pandas as pd

logging.basicConfig(level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')))
logger = logging.getLogger(__name__)

class WeatherConsumer:
    def __init__(self):
        # Конфигурация
        self.kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092').split(',')
        self.postgres_url = os.getenv('POSTGRES_URL')
        self.minio_endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
        self.minio_access_key = os.getenv('MINIO_ACCESS_KEY')
        self.minio_secret_key = os.getenv('MINIO_SECRET_KEY')
        self.minio_bucket = os.getenv('MINIO_BUCKET', 'weather-data')
        
        # Kafka topic
        self.topic = 'weather-data'
        self.consumer_group = 'weather-consumer-group'
        
        # Инициализация компонентов
        self.consumer = None
        self.postgres_conn = None
        self.minio_client = None

    def initialize(self):
        """Инициализация consumer"""
        try:
            # Kafka Consumer
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.kafka_servers,
                group_id=self.consumer_group,
                auto_offset_reset='latest',
                enable_auto_commit=False,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8')
            )
            
            # PostgreSQL connection
            if self.postgres_url:
                self.postgres_conn = psycopg2.connect(self.postgres_url)
                self.ensure_base_locations()
            
            # MinIO client
            if self.minio_access_key:
                self.minio_client = Minio(
                    self.minio_endpoint,
                    access_key=self.minio_access_key,
                    secret_key=self.minio_secret_key,
                    secure=False
                )
                self.init_minio()
            
            logger.info("Consumer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize consumer: {e}")
            raise

    def ensure_base_locations(self):
        """Создать базовые локации для городов из weather-producer"""
        base_locations = [
            {
                'location_name': 'Suceava Weather Station',
                'country': 'Romania',
                'region': 'Suceava',
                'city': 'Suceava', 
                'latitude': 47.6635,
                'longitude': 26.2519,
                'timezone': 'Europe/Bucharest'
            },
            {
                'location_name': 'Bucharest Weather Station',
                'country': 'Romania',
                'region': 'Bucuresti',
                'city': 'Bucharest',
                'latitude': 44.4268,
                'longitude': 26.1025,
                'timezone': 'Europe/Bucharest'
            },
            {
                'location_name': 'Cluj-Napoca Weather Station',
                'country': 'Romania', 
                'region': 'Cluj',
                'city': 'Cluj-Napoca',
                'latitude': 46.7712,
                'longitude': 23.6236,
                'timezone': 'Europe/Bucharest'
            },
            {
                'location_name': 'Iasi Weather Station',
                'country': 'Romania',
                'region': 'Iasi', 
                'city': 'Iasi',
                'latitude': 47.1585,
                'longitude': 27.6014,
                'timezone': 'Europe/Bucharest'
            },
            {
                'location_name': 'Constanta Weather Station',
                'country': 'Romania',
                'region': 'Constanta',
                'city': 'Constanta',
                'latitude': 44.1598,
                'longitude': 28.6348,
                'timezone': 'Europe/Bucharest'
            }
        ]

        try:
            with self.postgres_conn.cursor() as cur:
                for location in base_locations:
                    cur.execute("""
                        INSERT INTO locations (
                            location_name, country, region, city,
                            latitude, longitude, timezone,
                            campus_area, traffic_density, indoor_outdoor,
                            is_active
                        ) VALUES (
                            %(location_name)s, %(country)s, %(region)s, %(city)s,
                            %(latitude)s, %(longitude)s, %(timezone)s,
                            'outdoor', 'medium', 'outdoor', true
                        )
                        ON CONFLICT DO NOTHING
                    """, location)
                
                self.postgres_conn.commit()
                logger.info("Base weather locations ensured in database")
                
        except Exception as e:
            logger.error(f"Failed to ensure base locations: {e}")
            self.postgres_conn.rollback()
            raise

    def init_minio(self):
        """Создать bucket в MinIO"""
        try:
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
                logger.info(f"Created MinIO bucket: {self.minio_bucket}")
            else:
                logger.info(f"MinIO bucket already exists: {self.minio_bucket}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")

    def get_location_id(self, city_name, country='Romania'):
        """Получить location_id из базы данных"""
        try:
            with self.postgres_conn.cursor() as cur:
                # Попробуем найти по city
                cur.execute("""
                    SELECT location_id FROM locations 
                    WHERE LOWER(city) = LOWER(%s) AND country = %s
                    AND is_active = true
                    LIMIT 1
                """, (city_name, country))
                
                result = cur.fetchone()
                if result:
                    return result[0]
                
                # Если не нашли по city, попробуем по location_name
                cur.execute("""
                    SELECT location_id FROM locations 
                    WHERE LOWER(location_name) LIKE LOWER(%s) AND country = %s
                    AND is_active = true
                    LIMIT 1
                """, (f'%{city_name}%', country))
                
                result = cur.fetchone()
                return result[0] if result else None
                
        except Exception as e:
            logger.error(f"Failed to get location_id: {e}")
            return None

    def process_weather_event(self, weather_event):
        """Обработать одно погодное событие"""
        try:
            # Сохранить в PostgreSQL
            if self.postgres_conn:
                self.save_to_postgres(weather_event)
            
            # Сохранить в MinIO
            if self.minio_client:
                self.save_to_minio(weather_event)
                
            logger.debug(f"Processed event for {weather_event['location']['name']}")
            
        except Exception as e:
            logger.error(f"Failed to process weather event: {e}")
            raise

    def save_to_postgres(self, weather_event):
        """Сохранить данные в PostgreSQL используя схему weather_measurements"""
        try:
            location = weather_event['location']
            quality = weather_event['quality']
            
            # Получить location_id
            location_id = self.get_location_id(location['name'], location.get('country', 'Romania'))
            
            if not location_id:
                logger.warning(f"Location not found for {location['name']}, skipping weather data")
                return
            
            # Сохранить погодные данные в weather_measurements
            if weather_event['weather_data'] and 'current' in weather_event['weather_data']:
                current = weather_event['weather_data']['current']
                
                # Преобразовать время в правильный формат
                measurement_time = datetime.fromisoformat(
                    weather_event['timestamp'].replace('Z', '+00:00')
                )
                
                # Подготовить данные для вставки
                weather_data = {
                    'location_id': location_id,
                    'source': 'open_meteo',
                    'measurement_datetime': measurement_time,
                    'temperature': current.get('temperature_2m'),
                    'humidity': current.get('relative_humidity_2m'),
                    'apparent_temperature': current.get('apparent_temperature'),
                    'rainfall': current.get('precipitation', 0),
                    'windspeed': current.get('wind_speed_10m'),
                    'wind_direction': current.get('wind_direction_10m'),
                    'wind_gusts': current.get('wind_gusts_10m'),
                    'pressure_msl': current.get('pressure_msl'),
                    'surface_pressure': current.get('surface_pressure'),
                    'cloud_cover': current.get('cloud_cover'),
                    'visibility': None,  # Не предоставляется Open-Meteo
                    'uv_index': current.get('uv_index'),
                    'weather_code': current.get('weather_code'),
                    'is_day': current.get('is_day', 1) == 1,
                    'weather_api_source': 'open-meteo-api',
                    'quality_score': quality.get('completeness', 1.0),
                    'data_quality': 'good' if quality['status'] == 'success' else 'poor',
                    'raw_data_path': None,  # Путь к файлу в MinIO можно добавить позже
                    'api_response_time_ms': None
                }
                
                with self.postgres_conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO weather_measurements (
                            location_id, source, measurement_datetime,
                            temperature, humidity, apparent_temperature,
                            rainfall, windspeed, wind_direction, wind_gusts,
                            pressure_msl, surface_pressure, cloud_cover,
                            visibility, uv_index, weather_code, is_day,
                            weather_api_source, quality_score, data_quality,
                            raw_data_path, api_response_time_ms
                        ) VALUES (
                            %(location_id)s, %(source)s, %(measurement_datetime)s,
                            %(temperature)s, %(humidity)s, %(apparent_temperature)s,
                            %(rainfall)s, %(windspeed)s, %(wind_direction)s, %(wind_gusts)s,
                            %(pressure_msl)s, %(surface_pressure)s, %(cloud_cover)s,
                            %(visibility)s, %(uv_index)s, %(weather_code)s, %(is_day)s,
                            %(weather_api_source)s, %(quality_score)s, %(data_quality)s,
                            %(raw_data_path)s, %(api_response_time_ms)s
                        )
                    """, weather_data)
                
                self.postgres_conn.commit()
                logger.info(f"Saved weather data for {location['name']} to PostgreSQL")
            else:
                logger.warning(f"No current weather data for {location['name']}")
                
        except Exception as e:
            logger.error(f"Failed to save to PostgreSQL: {e}")
            self.postgres_conn.rollback()
            raise

    def save_to_minio(self, weather_event):
        """Сохранить данные в MinIO как JSON и Parquet"""
        try:
            location = weather_event['location']
            timestamp = datetime.fromisoformat(weather_event['timestamp'].replace('Z', '+00:00'))
            
            # Создать структуру папок: year/month/day/city/
            date_path = timestamp.strftime('%Y/%m/%d')
            city_name = location['name'].lower().replace(' ', '_').replace('-', '_')
            
            # Сохранить как JSON
            json_filename = f"{date_path}/{city_name}/{weather_event['event_id']}.json"
            json_data = BytesIO(json.dumps(weather_event, indent=2).encode('utf-8'))
            
            self.minio_client.put_object(
                bucket_name=self.minio_bucket,
                object_name=json_filename,
                data=json_data,
                length=json_data.getbuffer().nbytes,
                content_type='application/json'
            )
            
            # Создать DataFrame для Parquet (только если есть данные)
            if weather_event['weather_data'] and weather_event['quality']['status'] == 'success':
                df = self.create_dataframe(weather_event)
                if not df.empty:
                    parquet_filename = f"{date_path}/{city_name}/{weather_event['event_id']}.parquet"
                    parquet_buffer = BytesIO()
                    df.to_parquet(parquet_buffer, index=False)
                    parquet_buffer.seek(0)
                    
                    self.minio_client.put_object(
                        bucket_name=self.minio_bucket,
                        object_name=parquet_filename,
                        data=parquet_buffer,
                        length=parquet_buffer.getbuffer().nbytes,
                        content_type='application/octet-stream'
                    )
            
            logger.info(f"Saved weather data for {location['name']} to MinIO")
            
        except Exception as e:
            logger.error(f"Failed to save to MinIO: {e}")

    def create_dataframe(self, weather_event):
        """Создать DataFrame из погодных данных"""
        try:
            weather_data = weather_event['weather_data']
            location = weather_event['location']
            
            records = []
            
            # Текущие данные
            if 'current' in weather_data:
                current = weather_data['current']
                record = {
                    'event_id': weather_event['event_id'],
                    'timestamp': weather_event['timestamp'],
                    'city_name': location['name'],
                    'data_type': 'current',
                    'measurement_time': current.get('time'),
                    **{k: v for k, v in current.items() if k != 'time'}
                }
                records.append(record)
            
            # Почасовые данные (только первые несколько записей для экономии места)
            if 'hourly' in weather_data and 'time' in weather_data['hourly']:
                hourly = weather_data['hourly']
                times = hourly['time'][:24]  # Только первые 24 часа
                
                for i, time_point in enumerate(times):
                    record = {
                        'event_id': weather_event['event_id'],
                        'timestamp': weather_event['timestamp'],
                        'city_name': location['name'],
                        'data_type': 'hourly',
                        'measurement_time': time_point
                    }
                    
                    for key, values in hourly.items():
                        if key != 'time' and isinstance(values, list) and i < len(values):
                            record[key] = values[i]
                    
                    records.append(record)
            
            return pd.DataFrame(records) if records else pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Failed to create DataFrame: {e}")
            return pd.DataFrame()

    def start_consumer(self):
        """Запустить consumer"""
        logger.info("Starting Weather Consumer for UPGRADE project")
        
        self.initialize()
        
        logger.info(f"Consumer started, listening to topic: {self.topic}")
        
        try:
            for message in self.consumer:
                try:
                    weather_event = message.value
                    self.process_weather_event(weather_event)
                    
                    # Подтвердить обработку сообщения
                    self.consumer.commit()
                    
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
                    # Продолжаем работу даже если одно сообщение не обработалось
                    continue
                    
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Очистка ресурсов"""
        try:
            if self.consumer:
                self.consumer.close()
            if self.postgres_conn:
                self.postgres_conn.close()
            logger.info("Consumer cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

def main():
    consumer = WeatherConsumer()
    consumer.start_consumer()

if __name__ == "__main__":
    main()
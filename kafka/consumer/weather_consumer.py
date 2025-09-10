import json
import logging
import os
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
        self.kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092').split(',')
        self.postgres_url = os.getenv('POSTGRES_URL')
        self.minio_endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
        self.minio_access_key = os.getenv('MINIO_ACCESS_KEY')
        self.minio_secret_key = os.getenv('MINIO_SECRET_KEY')
        self.minio_bucket = os.getenv('MINIO_BUCKET', 'weather-data')
        
        self.topic = 'weather-data'
        self.consumer_group = 'weather-consumer-group'
        
        self.consumer = None
        self.postgres_conn = None
        self.minio_client = None

    def initialize(self):
        try:
            # Kafka Consumer - исправлен key_deserializer
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.kafka_servers,
                group_id=self.consumer_group,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                key_deserializer=lambda x: x.decode('utf-8') if x else None
            )
            logger.info("Kafka consumer initialized")
            
            # PostgreSQL connection
            if self.postgres_url:
                self.postgres_conn = psycopg2.connect(self.postgres_url)
                logger.info("PostgreSQL connected")
            
            # MinIO client
            if self.minio_access_key:
                self.minio_client = Minio(
                    self.minio_endpoint,
                    access_key=self.minio_access_key,
                    secret_key=self.minio_secret_key,
                    secure=False
                )
                self.init_minio()
                logger.info("MinIO connected")
            
            logger.info("Consumer initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize: %s", e)
            raise

    def init_minio(self):
        try:
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
                logger.info("Created MinIO bucket: %s", self.minio_bucket)
        except Exception as e:
            logger.error("MinIO init failed: %s", e)

    def get_location_id(self, city_name, country='Romania'):
        try:
            with self.postgres_conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Найти по city
                cur.execute("""
                    SELECT location_id FROM locations 
                    WHERE LOWER(city) = LOWER(%s) AND country = %s
                    AND is_active = true
                    LIMIT 1
                """, (city_name, country))
                
                result = cur.fetchone()
                if result:
                    logger.info("Found location_id: %s for %s (%s)", result['location_id'], city_name, country)
                    return result['location_id']
                
                # Найти по location_name без "Weather Station"
                cur.execute("""
                    SELECT location_id FROM locations 
                    WHERE LOWER(REPLACE(location_name, ' Weather Station', '')) = LOWER(%s) 
                    AND country = %s
                    AND is_active = true
                    LIMIT 1
                """, (city_name, country))
                
                result = cur.fetchone()
                if result:
                    logger.info("Found location_id: %s for %s (%s) via location_name", result['location_id'], city_name, country)
                    return result['location_id']
                
                # Найти по частичному совпадению
                cur.execute("""
                    SELECT location_id FROM locations 
                    WHERE LOWER(location_name) LIKE LOWER(%s) AND country = %s
                    AND is_active = true
                    LIMIT 1
                """, ('%' + city_name + '%', country))
                
                result = cur.fetchone()
                if result:
                    logger.info("Found location_id: %s for %s (%s) via partial match", result['location_id'], city_name, country)
                    return result['location_id']
                
                logger.warning("Location not found: %s (%s)", city_name, country)
                return None
                
        except Exception as e:
            logger.error("get_location_id failed for %s (%s): %s", city_name, country, e)
            return None

    def save_to_postgres(self, weather_event):
        try:
            location = weather_event['location']
            quality = weather_event['quality']
            
            # ИСПРАВЛЕНО: передаем страну из данных сообщения
            location_id = self.get_location_id(location['name'], location['country'])
            if not location_id:
                logger.error("No location_id for %s (%s)", location['name'], location['country'])
                return
            
            if not weather_event['weather_data'] or 'current' not in weather_event['weather_data']:
                logger.warning("No current weather data for %s (%s)", location['name'], location['country'])
                return
                
            current = weather_event['weather_data']['current']
            
            timestamp_str = weather_event['timestamp']
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str.replace('Z', '+00:00')
            measurement_time = datetime.fromisoformat(timestamp_str)
            
            with self.postgres_conn.cursor() as cur:
                # Проверить существование
                cur.execute("""
                    SELECT weather_id FROM weather_measurements 
                    WHERE location_id = %s AND measurement_datetime = %s
                """, (location_id, measurement_time))
                
                if cur.fetchone():
                    logger.info("Record already exists for %s (%s) at %s", location['name'], location['country'], measurement_time)
                    return
                
                # Вставить новую запись
                cur.execute("""
                    INSERT INTO weather_measurements (
                        location_id, source, measurement_datetime,
                        temperature, humidity, apparent_temperature,
                        rainfall, windspeed, wind_direction, wind_gusts,
                        pressure_msl, surface_pressure, cloud_cover,
                        uv_index, weather_code, is_day,
                        weather_api_source, quality_score, data_quality
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING weather_id
                """, (
                    location_id, 'open_meteo', measurement_time,
                    current.get('temperature_2m'), current.get('relative_humidity_2m'),
                    current.get('apparent_temperature'), current.get('precipitation', 0),
                    current.get('wind_speed_10m'), current.get('wind_direction_10m'),
                    current.get('wind_gusts_10m'), current.get('pressure_msl'),
                    current.get('surface_pressure'), current.get('cloud_cover'),
                    current.get('uv_index'), current.get('weather_code'),
                    current.get('is_day', 1) == 1, 'open-meteo-api',
                    quality.get('completeness', 1.0),
                    'good' if quality['status'] == 'success' else 'poor'
                ))
                
                weather_id = cur.fetchone()[0]
                self.postgres_conn.commit()
                logger.info("Saved weather data for %s (%s) - ID: %s", location['name'], location['country'], weather_id)
                
        except Exception as e:
            logger.error("Failed to save to PostgreSQL for %s: %s", location.get('name', 'unknown'), e)
            if self.postgres_conn:
                self.postgres_conn.rollback()

    def save_to_minio(self, weather_event):
        try:
            location = weather_event['location']
            timestamp = datetime.fromisoformat(weather_event['timestamp'].replace('Z', '+00:00'))
            
            date_path = timestamp.strftime('%Y/%m/%d')
            # Улучшена обработка названий городов с диакритическими знаками
            city_name = location['name'].lower().replace(' ', '_').replace('-', '_')
            # Убираем диакритические знаки для безопасных путей файлов
            city_name = ''.join(c for c in city_name if c.isalnum() or c == '_')
            
            json_filename = f"{date_path}/{city_name}/{weather_event['event_id']}.json"
            json_data = BytesIO(json.dumps(weather_event, indent=2, ensure_ascii=False).encode('utf-8'))
            
            self.minio_client.put_object(
                bucket_name=self.minio_bucket,
                object_name=json_filename,
                data=json_data,
                length=json_data.getbuffer().nbytes,
                content_type='application/json'
            )
            
            logger.info("Saved to MinIO: %s", json_filename)
            
        except Exception as e:
            logger.error("Failed to save to MinIO for %s: %s", location.get('name', 'unknown'), e)

    def process_weather_event(self, weather_event):
        try:
            event_id = weather_event.get('event_id', 'unknown')
            location_name = weather_event.get('location', {}).get('name', 'unknown')
            country = weather_event.get('location', {}).get('country', 'unknown')
            logger.info("Processing event %s for %s (%s)", event_id, location_name, country)
            
            if self.postgres_conn:
                self.save_to_postgres(weather_event)
            
            if self.minio_client:
                self.save_to_minio(weather_event)
                
        except Exception as e:
            logger.error("Failed to process event: %s", e)
            raise

    def start_consumer(self):
        logger.info("Starting Weather Consumer")
        
        self.initialize()
        
        try:
            logger.info("Starting to consume messages from topic: %s", self.topic)
            for message in self.consumer:
                try:
                    logger.info("Received message from partition %s, offset %s", 
                              message.partition, message.offset)
                    
                    weather_event = message.value
                    self.process_weather_event(weather_event)
                    self.consumer.commit()
                    
                except Exception as e:
                    logger.error("Failed to process message: %s", e)
                    continue
                    
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error("Consumer error: %s", e)
        finally:
            self.cleanup()

    def cleanup(self):
        try:
            if self.consumer:
                self.consumer.close()
            if self.postgres_conn:
                self.postgres_conn.close()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error("Cleanup error: %s", e)

def main():
    consumer = WeatherConsumer()
    consumer.start_consumer()

if __name__ == "__main__":
    main()
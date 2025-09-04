# weather_kafka_producer.py
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List
import uuid

import aiohttp
from kafka import KafkaProducer
from kafka.errors import KafkaError
import schedule
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WeatherKafkaProducer:
    def __init__(self):
        self.kafka_bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
        self.open_meteo_url = 'https://api.open-meteo.com/v1/forecast'
        
        # Kafka topics
        self.topics = {
            'raw_weather': 'weather-raw-data',
            'processed_weather': 'weather-processed-data',
            'weather_alerts': 'weather-alerts'
        }
        
        # Initialize Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap_servers.split(','),
            value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
            key_serializer=lambda x: x.encode('utf-8'),
            acks='all',
            retries=3,
            retry_backoff_ms=1000
        )
        
        # Romanian cities for monitoring
        self.cities = self._load_romania_cities()
        logger.info(f"Loaded {len(self.cities)} Romanian cities for monitoring")

    def _load_romania_cities(self) -> List[Dict]:
        """Load Romanian cities based on your database schema"""
        return [
            # Major cities aligned with your locations table structure
            {'location_id': 'RO-B', 'name': 'Bucharest', 'county': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025, 'elevation': 90, 'country': 'Romania'},
            {'location_id': 'RO-SV', 'name': 'Suceava', 'county': 'Suceava', 'lat': 47.6635, 'lon': 26.2535, 'elevation': 325, 'country': 'Romania'},
            {'location_id': 'RO-CJ', 'name': 'Cluj-Napoca', 'county': 'Cluj', 'lat': 46.7712, 'lon': 23.6236, 'elevation': 411, 'country': 'Romania'},
            {'location_id': 'RO-TM', 'name': 'Timisoara', 'county': 'Timis', 'lat': 45.7489, 'lon': 21.2087, 'elevation': 90, 'country': 'Romania'},
            {'location_id': 'RO-CT', 'name': 'Constanta', 'county': 'Constanta', 'lat': 44.1598, 'lon': 28.6348, 'elevation': 25, 'country': 'Romania'},
            {'location_id': 'RO-IS', 'name': 'Iasi', 'county': 'Iasi', 'lat': 47.1585, 'lon': 27.6014, 'elevation': 95, 'country': 'Romania'},
            {'location_id': 'RO-BV', 'name': 'Brasov', 'county': 'Brasov', 'lat': 45.6427, 'lon': 25.5887, 'elevation': 625, 'country': 'Romania'},
            {'location_id': 'RO-GL', 'name': 'Galati', 'county': 'Galati', 'lat': 45.4353, 'lon': 28.0080, 'elevation': 55, 'country': 'Romania'},
        ]

    async def fetch_weather_data(self, session: aiohttp.ClientSession, city: Dict) -> Dict:
        """Fetch comprehensive weather data for a city"""
        
        # Using comprehensive parameter set from our test
        params = {
            'latitude': city['lat'],
            'longitude': city['lon'],
            'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,precipitation,wind_speed_10m,wind_direction_10m,cloud_cover,surface_pressure,visibility',
            'hourly': 'temperature_2m,relative_humidity_2m,dew_point_2m,precipitation,weather_code,wind_speed_10m,cloud_cover,shortwave_radiation,uv_index,soil_temperature_0cm',
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,weather_code,sunrise,sunset,uv_index_max,shortwave_radiation_sum',
            'timezone': 'auto',
            'forecast_days': 3
        }
        
        try:
            async with session.get(self.open_meteo_url, params=params, timeout=15) as response:
                if response.status == 200:
                    weather_data = await response.json()
                    
                    # Create structured weather event for Kafka
                    weather_event = {
                        'event_id': str(uuid.uuid4()),
                        'measurement_id': f"WEATHER_{city['location_id']}_{int(time.time())}",
                        'location_id': city['location_id'],
                        'location_name': city['name'],
                        'county': city['county'],
                        'country': city['country'],
                        'coordinates': {
                            'latitude': city['lat'],
                            'longitude': city['lon'],
                            'elevation': city['elevation']
                        },
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'data_source': 'open-meteo-api',
                        'data_type': 'weather_comprehensive',
                        'collection_status': 'success',
                        'weather_data': weather_data,
                        'quality_score': self._calculate_data_quality(weather_data),
                        'processing_metadata': {
                            'api_version': 'v1',
                            'parameters_requested': len(params),
                            'response_time_ms': None,  # Can be calculated
                            'data_completeness': self._check_completeness(weather_data)
                        }
                    }
                    
                    logger.info(f"Successfully collected weather data for {city['name']} (quality: {weather_event['quality_score']:.2f})")
                    return weather_event
                    
                else:
                    return self._create_error_event(city, f"HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Error fetching data for {city['name']}: {e}")
            return self._create_error_event(city, str(e))

    def _calculate_data_quality(self, data: Dict) -> float:
        """Calculate data quality score"""
        total_fields = 0
        valid_fields = 0
        
        for section in ['current', 'hourly', 'daily']:
            if section in data:
                for key, value in data[section].items():
                    if key != 'time':
                        total_fields += 1
                        if value is not None:
                            valid_fields += 1
        
        return round(valid_fields / total_fields if total_fields > 0 else 0, 3)

    def _check_completeness(self, data: Dict) -> Dict:
        """Check data completeness by section"""
        completeness = {}
        
        for section in ['current', 'hourly', 'daily']:
            if section in data:
                section_data = data[section]
                if isinstance(section_data, dict):
                    total = len([k for k in section_data.keys() if k != 'time'])
                    valid = len([v for k, v in section_data.items() if k != 'time' and v is not None])
                    completeness[section] = round(valid / total if total > 0 else 0, 2)
        
        return completeness

    def _create_error_event(self, city: Dict, error_message: str) -> Dict:
        """Create error event"""
        return {
            'event_id': str(uuid.uuid4()),
            'measurement_id': f"WEATHER_{city['location_id']}_{int(time.time())}_ERROR",
            'location_id': city['location_id'],
            'location_name': city['name'],
            'county': city['county'],
            'country': city['country'],
            'coordinates': {
                'latitude': city['lat'],
                'longitude': city['lon'],
                'elevation': city['elevation']
            },
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data_source': 'open-meteo-api',
            'data_type': 'weather_comprehensive',
            'collection_status': 'error',
            'error_message': error_message,
            'weather_data': None,
            'quality_score': 0.0
        }

    async def collect_and_send_weather_data(self):
        """Collect weather data and send to Kafka"""
        logger.info(f"Starting weather data collection for {len(self.cities)} cities")
        
        async with aiohttp.ClientSession() as session:
            # Process cities in batches to avoid API overload
            batch_size = 3
            successful = 0
            failed = 0
            
            for i in range(0, len(self.cities), batch_size):
                batch = self.cities[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(self.cities) + batch_size - 1)//batch_size}")
                
                tasks = [self.fetch_weather_data(session, city) for city in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Task failed: {result}")
                        failed += 1
                        continue
                    
                    try:
                        # Send raw data to Kafka
                        future = self.producer.send(
                            topic=self.topics['raw_weather'],
                            key=result['location_id'],
                            value=result
                        )
                        
                        # Wait for acknowledgment
                        record_metadata = future.get(timeout=10)
                        logger.info(f"Sent {result['measurement_id']} to partition {record_metadata.partition}")
                        
                        # Create processed event for analytics
                        processed_event = self._create_processed_event(result)
                        
                        self.producer.send(
                            topic=self.topics['processed_weather'],
                            key=result['location_id'],
                            value=processed_event
                        )
                        
                        # Check for alerts (extreme conditions)
                        alert_event = self._check_weather_alerts(result)
                        if alert_event:
                            self.producer.send(
                                topic=self.topics['weather_alerts'],
                                key=result['location_id'],
                                value=alert_event
                            )
                        
                        successful += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to send to Kafka: {e}")
                        failed += 1
                
                # Small delay between batches
                await asyncio.sleep(1)
            
            # Ensure all messages are sent
            self.producer.flush()
            
            logger.info(f"Weather collection completed. Success: {successful}, Failed: {failed}")

    def _create_processed_event(self, raw_event: Dict) -> Dict:
        """Create processed event for analytics"""
        if raw_event['collection_status'] != 'success':
            return raw_event
            
        weather_data = raw_event['weather_data']
        current = weather_data.get('current', {})
        
        # Extract key metrics for analytics
        processed = {
            'event_id': raw_event['event_id'],
            'measurement_id': raw_event['measurement_id'],
            'location_id': raw_event['location_id'],
            'timestamp': raw_event['timestamp'],
            'metrics': {
                'temperature': current.get('temperature_2m'),
                'humidity': current.get('relative_humidity_2m'),
                'wind_speed': current.get('wind_speed_10m'),
                'wind_direction': current.get('wind_direction_10m'),
                'pressure': current.get('surface_pressure'),
                'visibility': current.get('visibility'),
                'cloud_cover': current.get('cloud_cover'),
                'weather_code': current.get('weather_code'),
                'precipitation': current.get('precipitation')
            },
            'quality_indicators': {
                'data_quality_score': raw_event['quality_score'],
                'completeness': raw_event['processing_metadata']['data_completeness']
            }
        }
        
        return processed

    def _check_weather_alerts(self, weather_event: Dict) -> Dict:
        """Check for extreme weather conditions"""
        if weather_event['collection_status'] != 'success':
            return None
            
        current = weather_event['weather_data'].get('current', {})
        alerts = []
        
        # Temperature alerts
        temp = current.get('temperature_2m')
        if temp is not None:
            if temp > 35:
                alerts.append({'type': 'high_temperature', 'value': temp, 'threshold': 35, 'severity': 'warning'})
            elif temp < -10:
                alerts.append({'type': 'low_temperature', 'value': temp, 'threshold': -10, 'severity': 'warning'})
        
        # Wind alerts
        wind = current.get('wind_speed_10m')
        if wind is not None and wind > 50:
            alerts.append({'type': 'high_wind', 'value': wind, 'threshold': 50, 'severity': 'warning'})
        
        # Precipitation alerts
        precip = current.get('precipitation')
        if precip is not None and precip > 10:
            alerts.append({'type': 'heavy_precipitation', 'value': precip, 'threshold': 10, 'severity': 'info'})
        
        if not alerts:
            return None
            
        return {
            'event_id': str(uuid.uuid4()),
            'source_event_id': weather_event['event_id'],
            'location_id': weather_event['location_id'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'alert_type': 'weather_extreme',
            'alerts': alerts,
            'location_name': weather_event['location_name']
        }

    def start_scheduler(self):
        """Start scheduled weather data collection"""
        logger.info("Starting weather data collection scheduler")
        
        # Schedule collection every 30 minutes
        schedule.every(30).minutes.do(lambda: asyncio.run(self.collect_and_send_weather_data()))
        
        # Run initial collection
        logger.info("Running initial collection...")
        asyncio.run(self.collect_and_send_weather_data())
        
        # Keep scheduler running
        while True:
            schedule.run_pending()
            time.sleep(60)

    def close(self):
        """Close Kafka producer"""
        if self.producer:
            self.producer.close()


if __name__ == "__main__":
    producer = WeatherKafkaProducer()
    try:
        producer.start_scheduler()
    except KeyboardInterrupt:
        logger.info("Shutting down weather producer")
        producer.close()
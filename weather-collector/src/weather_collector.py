import io
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from minio import Minio
from minio.error import S3Error
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/weather_collector.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


class Config:
    """Weather Collector Configuration"""
    
    def __init__(self):
        # MinIO Configuration
        self.minio_endpoint = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
        self.minio_access_key = os.getenv('MINIO_ACCESS_KEY', 'minio_upgrade_admin')
        self.minio_secret_key = os.getenv('MINIO_SECRET_KEY', 'minio_upgrade_password')
        self.minio_bucket = os.getenv('MINIO_BUCKET', 'upgrade-raw')
        self.minio_secure = os.getenv('MINIO_SECURE', 'false').lower() == 'true'
        
        # API Configuration
        self.api_base_url = os.getenv('API_BASE_URL', 'https://api.open-meteo.com/v1')
        self.api_timeout = int(os.getenv('API_TIMEOUT', '30'))
        
        # Collection Configuration
        self.batch_size = int(os.getenv('BATCH_SIZE', '50'))
        self.rate_limit_delay = float(os.getenv('RATE_LIMIT_DELAY', '0.1'))
        
        # Storage Configuration
        self.save_json = os.getenv('SAVE_JSON', 'true').lower() == 'true'
        self.save_parquet = os.getenv('SAVE_PARQUET', 'true').lower() == 'true'
        self.parquet_compression = os.getenv('PARQUET_COMPRESSION', 'snappy')
        
        # Data Configuration
        self.cities_file = os.getenv('CITIES_FILE', '/app/data/cities.json')
        self.timezone = os.getenv('TIMEZONE', 'Europe/Bucharest')


class MinIOClient:
    """MinIO client for storing weather data in multiple formats"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = Minio(
            config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure
        )
        self._ensure_bucket_exists()
        logger.info(f"MinIO client initialized: {config.minio_endpoint}")
    
    def _ensure_bucket_exists(self):
        """Ensure the bucket exists"""
        try:
            if not self.client.bucket_exists(self.config.minio_bucket):
                self.client.make_bucket(self.config.minio_bucket)
                logger.info(f"Created bucket: {self.config.minio_bucket}")
        except S3Error as e:
            logger.error(f"Error with bucket: {e}")
            raise
    
    def _create_object_path(self, format_type: str, country: str, timestamp: datetime, filename: str) -> str:
        """Create standardized object path"""
        return (
            f"raw/weather/"
            f"format={format_type}/"
            f"country={country}/"
            f"year={timestamp.year}/"
            f"month={timestamp.month:02d}/"
            f"day={timestamp.day:02d}/"
            f"hour={timestamp.hour:02d}/"
            f"{filename}"
        )
    
    def save_json_data(self, country: str, city: str, data: Dict, timestamp: datetime) -> str:
        """Save individual city data as JSON"""
        safe_city_name = city.lower().replace(' ', '_').replace('-', '_')
        filename = f"{safe_city_name}.json"
        object_path = self._create_object_path('json', country, timestamp, filename)
        
        try:
            enriched_data = {
                "metadata": {
                    "collection_timestamp": timestamp.isoformat(),
                    "country": country,
                    "city": city,
                    "collector_version": "1.1.0",
                    "api_source": "open-meteo.com"
                },
                "raw_data": data
            }
            
            json_data = json.dumps(enriched_data, indent=2, ensure_ascii=False)
            json_bytes = json_data.encode('utf-8')
            
            self.client.put_object(
                bucket_name=self.config.minio_bucket,
                object_name=object_path,
                data=json_bytes,
                length=len(json_bytes),
                content_type="application/json"
            )
            
            logger.debug(f"Saved JSON: {object_path}")
            return object_path
            
        except Exception as e:
            logger.error(f"Failed to save JSON data: {e}")
            raise
    
    def save_parquet_batch(self, weather_batch: List[Dict], timestamp: datetime, country: str) -> str:
        """Save batch of weather data as Parquet file"""
        filename = f"weather_batch.parquet"
        object_path = self._create_object_path('parquet', country, timestamp, filename)
        
        try:
            # Convert to DataFrame
            df = self._convert_to_dataframe(weather_batch, timestamp)
            
            # Convert to Parquet bytes
            parquet_buffer = io.BytesIO()
            df.to_parquet(
                parquet_buffer,
                engine='pyarrow',
                compression=self.config.parquet_compression,
                index=False
            )
            parquet_bytes = parquet_buffer.getvalue()
            
            # Upload to MinIO
            self.client.put_object(
                bucket_name=self.config.minio_bucket,
                object_name=object_path,
                data=parquet_bytes,
                length=len(parquet_bytes),
                content_type="application/octet-stream",
                metadata={
                    "format": "parquet",
                    "country": country,
                    "collection-timestamp": timestamp.isoformat(),
                    "record-count": str(len(weather_batch))
                }
            )
            
            logger.info(f"Saved Parquet: {object_path} ({len(weather_batch)} records, {len(parquet_bytes)} bytes)")
            return object_path
            
        except Exception as e:
            logger.error(f"Failed to save Parquet data: {e}")
            raise
    
    def _convert_to_dataframe(self, weather_batch: List[Dict], collection_timestamp: datetime) -> pd.DataFrame:
        """Convert weather data batch to normalized DataFrame"""
        records = []
        
        for item in weather_batch:
            city_data = item['city_data']
            weather_data = item['weather_data']
            
            # Extract current weather data
            current = weather_data.get('current', {})
            
            record = {
                # Collection metadata
                'collection_timestamp': collection_timestamp.isoformat(),
                'collection_date': collection_timestamp.date(),
                'collection_hour': collection_timestamp.hour,
                
                # Location data
                'country': city_data['country'],
                'city': city_data['name'],
                'latitude': city_data['latitude'],
                'longitude': city_data['longitude'],
                'population': city_data.get('population'),
                
                # Weather measurements
                'temperature_2m': current.get('temperature_2m'),
                'relative_humidity_2m': current.get('relative_humidity_2m'),
                'precipitation': current.get('precipitation', 0),
                'surface_pressure': current.get('surface_pressure'),
                'wind_speed_10m': current.get('wind_speed_10m'),
                'wind_direction_10m': current.get('wind_direction_10m'),
                'weather_code': current.get('weather_code'),
                
                # API metadata
                'api_time': current.get('time'),
                'api_interval': current.get('interval'),
                
                # Data quality
                'data_complete': all([
                    current.get('temperature_2m') is not None,
                    current.get('relative_humidity_2m') is not None,
                    current.get('surface_pressure') is not None
                ])
            }
            
            records.append(record)
        
        df = pd.DataFrame(records)
        
        # Optimize data types
        df['collection_date'] = pd.to_datetime(df['collection_date'])
        df['collection_hour'] = df['collection_hour'].astype('int8')
        df['latitude'] = df['latitude'].astype('float32')
        df['longitude'] = df['longitude'].astype('float32')
        df['temperature_2m'] = df['temperature_2m'].astype('float32')
        df['relative_humidity_2m'] = df['relative_humidity_2m'].astype('float32')
        df['precipitation'] = df['precipitation'].astype('float32')
        df['surface_pressure'] = df['surface_pressure'].astype('float32')
        df['wind_speed_10m'] = df['wind_speed_10m'].astype('float32')
        df['wind_direction_10m'] = df['wind_direction_10m'].astype('float32')
        df['weather_code'] = df['weather_code'].astype('int16')
        df['data_complete'] = df['data_complete'].astype('bool')
        
        return df


class WeatherAPIClient:
    """Client for Open-Meteo Weather API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UPGRADE-Weather-Collector/1.1.0',
            'Accept': 'application/json'
        })
        self.stats = {'total_requests': 0, 'successful_requests': 0, 'failed_requests': 0}
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def fetch_weather_data(self, city_data: Dict) -> Optional[Dict]:
        """Fetch weather data for a single city"""
        params = {
            'latitude': city_data['latitude'],
            'longitude': city_data['longitude'],
            'current': [
                'temperature_2m',
                'relative_humidity_2m',
                'precipitation',
                'surface_pressure', 
                'wind_speed_10m',
                'wind_direction_10m',
                'weather_code'
            ],
            'timezone': self.config.timezone
        }
        
        url = f"{self.config.api_base_url}/forecast"
        
        try:
            self.stats['total_requests'] += 1
            
            response = self.session.get(url, params=params, timeout=self.config.api_timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if 'current' not in data:
                raise ValueError("Invalid API response: missing 'current' data")
            
            self.stats['successful_requests'] += 1
            return data
            
        except Exception as e:
            self.stats['failed_requests'] += 1
            logger.error(f"API request failed for {city_data['name']}: {e}")
            raise


class WeatherCollector:
    """Main Weather Collector with Parquet support"""
    
    def __init__(self, config: Config):
        self.config = config
        self.minio_client = MinIOClient(config)
        self.api_client = WeatherAPIClient(config)
        
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_cities': 0,
            'successful_cities': 0,
            'failed_cities': 0,
            'json_files_saved': 0,
            'parquet_files_saved': 0
        }
    
    def load_cities(self) -> List[Dict]:
        """Load cities from JSON file"""
        try:
            with open(self.config.cities_file, 'r', encoding='utf-8') as f:
                cities_data = json.load(f)
            
            cities = cities_data.get('cities', [])
            logger.info(f"Loaded {len(cities)} cities from {self.config.cities_file}")
            return cities
            
        except Exception as e:
            logger.error(f"Failed to load cities: {e}")
            raise
    
    def process_cities_batch(self, cities_batch: List[Dict], collection_timestamp: datetime) -> Tuple[int, int]:
        """Process a batch of cities and save in both formats"""
        successful = 0
        failed = 0
        weather_batch_data = []
        
        # Group cities by country for Parquet optimization
        cities_by_country = {}
        for city in cities_batch:
            country = city['country']
            if country not in cities_by_country:
                cities_by_country[country] = []
            cities_by_country[country].append(city)
        
        # Process each country group
        for country, country_cities in cities_by_country.items():
            country_weather_data = []
            
            for i, city in enumerate(country_cities, 1):
                try:
                    # Rate limiting
                    if i > 1:
                        time.sleep(self.config.rate_limit_delay)
                    
                    logger.info(f"Processing {city['name']}, {country} ({i}/{len(country_cities)})")
                    
                    # Fetch weather data
                    weather_data = self.api_client.fetch_weather_data(city)
                    
                    if weather_data:
                        # Save individual JSON file if enabled
                        if self.config.save_json:
                            self.minio_client.save_json_data(
                                country=country,
                                city=city['name'],
                                data=weather_data,
                                timestamp=collection_timestamp
                            )
                            self.stats['json_files_saved'] += 1
                        
                        # Add to batch for Parquet
                        if self.config.save_parquet:
                            country_weather_data.append({
                                'city_data': city,
                                'weather_data': weather_data
                            })
                        
                        successful += 1
                        logger.info(f"✓ Successfully processed {city['name']}, {country}")
                    else:
                        failed += 1
                        logger.warning(f"✗ No data received for {city['name']}, {country}")
                
                except Exception as e:
                    failed += 1
                    logger.error(f"✗ Failed to process {city['name']}, {country}: {e}")
            
            # Save country batch as Parquet
            if self.config.save_parquet and country_weather_data:
                try:
                    self.minio_client.save_parquet_batch(
                        country_weather_data, 
                        collection_timestamp, 
                        country
                    )
                    self.stats['parquet_files_saved'] += 1
                except Exception as e:
                    logger.error(f"Failed to save Parquet batch for {country}: {e}")
        
        return successful, failed
    
    def run_collection(self) -> Dict:
        """Main collection process"""
        logger.info("=" * 60)
        logger.info("UPGRADE WEATHER COLLECTOR WITH PARQUET SUPPORT")
        logger.info("=" * 60)
        
        self.stats['start_time'] = datetime.now(timezone.utc)
        collection_timestamp = self.stats['start_time']
        
        try:
            # Load cities
            cities = self.load_cities()
            self.stats['total_cities'] = len(cities)
            
            logger.info(f"Collection configuration:")
            logger.info(f"  - Total cities: {len(cities)}")
            logger.info(f"  - Batch size: {self.config.batch_size}")
            logger.info(f"  - Save JSON: {self.config.save_json}")
            logger.info(f"  - Save Parquet: {self.config.save_parquet}")
            logger.info(f"  - Parquet compression: {self.config.parquet_compression}")
            
            # Process cities in batches
            total_successful = 0
            total_failed = 0
            
            for i in range(0, len(cities), self.config.batch_size):
                batch = cities[i:i + self.config.batch_size]
                batch_num = (i // self.config.batch_size) + 1
                total_batches = (len(cities) + self.config.batch_size - 1) // self.config.batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} cities)")
                
                successful, failed = self.process_cities_batch(batch, collection_timestamp)
                total_successful += successful
                total_failed += failed
                
                logger.info(f"Batch {batch_num} completed: {successful} successful, {failed} failed")
            
            # Final statistics
            self.stats['end_time'] = datetime.now(timezone.utc)
            self.stats['successful_cities'] = total_successful
            self.stats['failed_cities'] = total_failed
            
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            api_stats = self.api_client.stats
            
            logger.info("=" * 60)
            logger.info("COLLECTION COMPLETED")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Cities: {total_successful}/{len(cities)} successful")
            logger.info(f"API requests: {api_stats['successful_requests']}/{api_stats['total_requests']}")
            logger.info(f"Files saved:")
            logger.info(f"  - JSON files: {self.stats['json_files_saved']}")
            logger.info(f"  - Parquet files: {self.stats['parquet_files_saved']}")
            logger.info("=" * 60)
            
            return self.stats
            
        except Exception as e:
            logger.error(f"Collection failed: {e}")
            raise


def main():
    """Main entry point"""
    try:
        config = Config()
        collector = WeatherCollector(config)
        stats = collector.run_collection()
        
        # Exit with appropriate code
        if stats['failed_cities'] == 0:
            logger.info("Collection completed successfully")
            sys.exit(0)
        else:
            logger.warning(f"Collection completed with {stats['failed_cities']} failures")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Collection interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
# weather-producer/enhanced_app_csv.py
import asyncio
import json
import logging
import os
import csv
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List
from pathlib import Path

import aiohttp
import schedule
import time

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnhancedWeatherProducerCSV:
    def __init__(self):
        self.open_meteo_url = os.getenv('OPEN_METEO_API_URL', 'https://api.open-meteo.com/v1/forecast')
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './weather_data'))
        self.output_dir.mkdir(exist_ok=True)
        
        # CSV files for different data types
        self.csv_files = {
            'summary': self.output_dir / 'weather_summary.csv',
            'current': self.output_dir / 'weather_current.csv',
            'hourly': self.output_dir / 'weather_hourly.csv',
            'daily': self.output_dir / 'weather_daily.csv',
            'metadata': self.output_dir / 'weather_metadata.csv'
        }
        
        # Initialize CSV files with headers if they don't exist
        self._initialize_csv_files()
        
        # Extended Romanian cities with comprehensive coverage
        self.cities = self._load_romania_cities()
        logger.info(f"Loaded {len(self.cities)} Romanian cities for monitoring")

    def _initialize_csv_files(self):
        """Initialize CSV files with headers if they don't exist"""
        
        # Summary CSV headers
        summary_headers = [
            'event_id', 'city_id', 'city_name', 'county', 'country', 'latitude', 'longitude',
            'elevation', 'timestamp', 'collection_status', 'data_richness_score',
            'geographic_zone', 'climate_zone', 'error_message'
        ]
        
        # Current weather headers
        current_headers = [
            'event_id', 'city_id', 'timestamp', 'temperature_2m', 'relative_humidity_2m',
            'apparent_temperature', 'is_day', 'precipitation', 'rain', 'showers', 'snowfall',
            'weather_code', 'cloud_cover', 'surface_pressure', 'sea_level_pressure',
            'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m'
        ]
        
        # Hourly data headers (we'll add row_timestamp for the specific hour)
        hourly_headers = [
            'event_id', 'city_id', 'collection_timestamp', 'row_timestamp', 'temperature_2m',
            'relative_humidity_2m', 'dew_point_2m', 'apparent_temperature', 'pressure_msl',
            'surface_pressure', 'cloud_cover', 'visibility', 'wind_speed_10m', 'wind_direction_10m',
            'wind_gusts_10m', 'precipitation', 'rain', 'showers', 'snowfall', 'weather_code',
            'shortwave_radiation', 'uv_index', 'soil_temperature_0cm', 'soil_moisture_0_1cm'
        ]
        
        # Daily data headers
        daily_headers = [
            'event_id', 'city_id', 'collection_timestamp', 'date', 'weather_code',
            'temperature_2m_max', 'temperature_2m_min', 'apparent_temperature_max',
            'apparent_temperature_min', 'sunrise', 'sunset', 'precipitation_sum',
            'rain_sum', 'snowfall_sum', 'wind_speed_10m_max', 'wind_gusts_10m_max'
        ]
        
        # Metadata headers
        metadata_headers = [
            'city_id', 'city_name', 'county', 'country', 'latitude', 'longitude',
            'elevation', 'geographic_zone', 'climate_zone', 'last_updated'
        ]
        
        headers_map = {
            'summary': summary_headers,
            'current': current_headers,
            'hourly': hourly_headers,
            'daily': daily_headers,
            'metadata': metadata_headers
        }
        
        for file_type, headers in headers_map.items():
            csv_file = self.csv_files[file_type]
            if not csv_file.exists():
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                logger.info(f"Created {file_type} CSV file: {csv_file}")

    def _load_romania_cities(self) -> List[Dict]:
        """Load comprehensive Romanian cities for weather monitoring"""
        romania_cities = [
            # Major cities
            {'id': 'ro_bucharest', 'name': 'Bucharest', 'county': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025, 'elevation': 90},
            {'id': 'ro_suceava', 'name': 'Suceava', 'county': 'Suceava', 'lat': 47.6635, 'lon': 26.2535, 'elevation': 325},
            {'id': 'ro_cluj', 'name': 'Cluj-Napoca', 'county': 'Cluj', 'lat': 46.7712, 'lon': 23.6236, 'elevation': 411},
            {'id': 'ro_timisoara', 'name': 'Timisoara', 'county': 'Timis', 'lat': 45.7489, 'lon': 21.2087, 'elevation': 90},
            {'id': 'ro_constanta', 'name': 'Constanta', 'county': 'Constanta', 'lat': 44.1598, 'lon': 28.6348, 'elevation': 25},
            {'id': 'ro_iasi', 'name': 'Iasi', 'county': 'Iasi', 'lat': 47.1585, 'lon': 27.6014, 'elevation': 95},
            {'id': 'ro_brasov', 'name': 'Brasov', 'county': 'Brasov', 'lat': 45.6427, 'lon': 25.5887, 'elevation': 625},
            {'id': 'ro_galati', 'name': 'Galati', 'county': 'Galati', 'lat': 45.4353, 'lon': 28.0080, 'elevation': 55},
            {'id': 'ro_craiova', 'name': 'Craiova', 'county': 'Dolj', 'lat': 44.3302, 'lon': 23.7949, 'elevation': 100},
            {'id': 'ro_ploiesti', 'name': 'Ploiesti', 'county': 'Prahova', 'lat': 44.9447, 'lon': 26.0140, 'elevation': 150},
            
            # Regional centers
            {'id': 'ro_oradea', 'name': 'Oradea', 'county': 'Bihor', 'lat': 47.0465, 'lon': 21.9189, 'elevation': 150},
            {'id': 'ro_bacau', 'name': 'Bacau', 'county': 'Bacau', 'lat': 46.5670, 'lon': 26.9146, 'elevation': 165},
            {'id': 'ro_pitesti', 'name': 'Pitesti', 'county': 'Arges', 'lat': 44.8565, 'lon': 24.8692, 'elevation': 287},
            {'id': 'ro_arad', 'name': 'Arad', 'county': 'Arad', 'lat': 46.1866, 'lon': 21.3123, 'elevation': 117},
            {'id': 'ro_sibiu', 'name': 'Sibiu', 'county': 'Sibiu', 'lat': 45.7983, 'lon': 24.1256, 'elevation': 415},
            {'id': 'ro_targu_mures', 'name': 'Targu Mures', 'county': 'Mures', 'lat': 46.5425, 'lon': 24.5579, 'elevation': 308},
            {'id': 'ro_baia_mare', 'name': 'Baia Mare', 'county': 'Maramures', 'lat': 47.6587, 'lon': 23.5681, 'elevation': 225},
            {'id': 'ro_buzau', 'name': 'Buzau', 'county': 'Buzau', 'lat': 45.1561, 'lon': 26.8206, 'elevation': 95},
            {'id': 'ro_botosani', 'name': 'Botosani', 'county': 'Botosani', 'lat': 47.7482, 'lon': 26.6618, 'elevation': 130},
            {'id': 'ro_satu_mare', 'name': 'Satu Mare', 'county': 'Satu Mare', 'lat': 47.7930, 'lon': 22.8574, 'elevation': 123},
            
            # Additional coverage for geographic diversity
            {'id': 'ro_rm_valcea', 'name': 'Ramnicu Valcea', 'county': 'Valcea', 'lat': 45.1069, 'lon': 24.3699, 'elevation': 250},
            {'id': 'ro_drobeta', 'name': 'Drobeta-Turnu Severin', 'county': 'Mehedinti', 'lat': 44.6310, 'lon': 22.6563, 'elevation': 65},
            {'id': 'ro_piatra_neamt', 'name': 'Piatra Neamt', 'county': 'Neamt', 'lat': 46.9268, 'lon': 26.3681, 'elevation': 345},
            {'id': 'ro_tulcea', 'name': 'Tulcea', 'county': 'Tulcea', 'lat': 45.1667, 'lon': 28.8000, 'elevation': 30},
            {'id': 'ro_alba_iulia', 'name': 'Alba Iulia', 'county': 'Alba', 'lat': 46.0648, 'lon': 23.5717, 'elevation': 330},
            {'id': 'ro_deva', 'name': 'Deva', 'county': 'Hunedoara', 'lat': 45.8761, 'lon': 22.8972, 'elevation': 230},
            {'id': 'ro_focsani', 'name': 'Focsani', 'county': 'Vrancea', 'lat': 45.6943, 'lon': 27.1843, 'elevation': 55},
            {'id': 'ro_miercurea_ciuc', 'name': 'Miercurea Ciuc', 'county': 'Harghita', 'lat': 46.3558, 'lon': 25.8003, 'elevation': 661},
            
            # Mountain/coastal/border locations for climate diversity
            {'id': 'ro_predeal', 'name': 'Predeal', 'county': 'Brasov', 'lat': 45.5089, 'lon': 25.5700, 'elevation': 1110},
            {'id': 'ro_mamaia', 'name': 'Mamaia', 'county': 'Constanta', 'lat': 44.2508, 'lon': 28.6561, 'elevation': 10},
            {'id': 'ro_sinaia', 'name': 'Sinaia', 'county': 'Prahova', 'lat': 45.3500, 'lon': 25.5500, 'elevation': 800}
        ]
        
        return romania_cities

    async def fetch_comprehensive_weather_data(self, session: aiohttp.ClientSession, city: Dict) -> Dict:
        """Fetch comprehensive weather data with simplified parameters for better reliability"""
        
        # Simplified parameters - start with basic ones that definitely work
        current_params = [
            'temperature_2m', 'relative_humidity_2m', 'apparent_temperature',
            'precipitation', 'weather_code', 'cloud_cover', 'wind_speed_10m'
        ]
        
        hourly_params = [
            'temperature_2m', 'relative_humidity_2m', 'precipitation',
            'weather_code', 'wind_speed_10m'
        ]
        
        daily_params = [
            'weather_code', 'temperature_2m_max', 'temperature_2m_min',
            'precipitation_sum', 'wind_speed_10m_max'
        ]
        
        params = {
            'latitude': city['lat'],
            'longitude': city['lon'],
            'current': ','.join(current_params),
            'hourly': ','.join(hourly_params),
            'daily': ','.join(daily_params),
            'timezone': 'auto',  # Use auto instead of Europe/Bucharest
            'forecast_days': 1  # Reduce to 1 day to avoid quota issues
        }
        
        # Debug: log the request URL
        url_with_params = f"{self.open_meteo_url}?" + "&".join([f"{k}={v}" for k, v in params.items()])
        logger.debug(f"Requesting: {url_with_params[:200]}...")  # Truncate long URLs
        
        try:
            # Add SSL context that's more permissive
            connector = aiohttp.TCPConnector(ssl=False)  # Disable SSL verification for testing
            
            async with session.get(self.open_meteo_url, params=params, timeout=30, connector=connector) as response:
                response_text = await response.text()
                logger.debug(f"Response status for {city['name']}: {response.status}")
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        
                        # Enrich with comprehensive metadata
                        weather_event = {
                            'event_id': f"{city['id']}_{int(time.time())}",
                            'city_id': city['id'],
                            'city_name': city['name'],
                            'county': city['county'],
                            'country': 'Romania',
                            'latitude': city['lat'],
                            'longitude': city['lon'],
                            'elevation': city['elevation'],
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'data_source': 'open-meteo-simplified',
                            'raw_data': data,
                            'collection_status': 'success',
                            'data_richness_score': self._calculate_data_richness(data),
                            'geographic_zone': self._classify_geographic_zone(city),
                            'climate_zone': self._classify_climate_zone(city)
                        }
                        
                        logger.info(f"✓ Successfully collected data for {city['name']}, {city['county']} "
                                  f"(richness: {weather_event['data_richness_score']:.2f})")
                        return weather_event
                    except json.JSONDecodeError as je:
                        logger.error(f"JSON decode error for {city['name']}: {je}")
                        logger.error(f"Response text: {response_text[:500]}")
                        return self._create_error_event(city, f"JSON decode error: {je}")
                        
                else:
                    logger.error(f"✗ API error for {city['name']}: HTTP {response.status}")
                    logger.error(f"Response text: {response_text[:500]}")
                    return self._create_error_event(city, f"HTTP {response.status}: {response_text[:200]}")
                    
        except asyncio.TimeoutError:
            logger.error(f"✗ Timeout fetching data for {city['name']}")
            return self._create_error_event(city, "API timeout")
        except aiohttp.ClientConnectorError as ce:
            logger.error(f"✗ Connection error for {city['name']}: {ce}")
            return self._create_error_event(city, f"Connection error: {ce}")
        except Exception as e:
            logger.error(f"✗ Unexpected error fetching data for {city['name']}: {str(e)}")
            return self._create_error_event(city, str(e))

    def _calculate_data_richness(self, data: Dict) -> float:
        """Calculate data richness score based on available parameters"""
        total_params = 0
        available_params = 0
        
        # Check current data
        if 'current' in data:
            current = data['current']
            for key, value in current.items():
                if key != 'time':
                    total_params += 1
                    if value is not None:
                        available_params += 1
        
        # Check hourly data availability
        if 'hourly' in data and 'time' in data['hourly']:
            hourly_time_points = len(data['hourly']['time'])
            for key, values in data['hourly'].items():
                if key != 'time' and isinstance(values, list):
                    total_params += 1
                    non_null_values = sum(1 for v in values if v is not None)
                    # Score based on completeness of time series
                    if non_null_values > hourly_time_points * 0.8:  # >80% complete
                        available_params += 1
                    elif non_null_values > hourly_time_points * 0.5:  # >50% complete
                        available_params += 0.5
        
        # Check daily data
        if 'daily' in data:
            for key, value in data['daily'].items():
                if key != 'time':
                    total_params += 1
                    if isinstance(value, list) and any(v is not None for v in value):
                        available_params += 1
                    elif value is not None:
                        available_params += 1
        
        return round(available_params / total_params if total_params > 0 else 0, 3)

    def _classify_geographic_zone(self, city: Dict) -> str:
        """Classify city by geographic zone"""
        lat, lon, elev = city['lat'], city['lon'], city['elevation']
        
        if elev > 600:
            return 'mountain'
        elif lon > 28:
            return 'coastal'
        elif lat > 47:
            return 'northern'
        elif lat < 45:
            return 'southern'
        elif lon < 23:
            return 'western'
        else:
            return 'central'

    def _classify_climate_zone(self, city: Dict) -> str:
        """Classify city by climate characteristics"""
        lat, elev = city['lat'], city['elevation']
        
        if elev > 800:
            return 'alpine'
        elif elev > 400:
            return 'highland'
        elif lat > 47:
            return 'continental_north'
        elif lat < 45:
            return 'continental_south'
        else:
            return 'temperate_continental'

    def _create_error_event(self, city: Dict, error_message: str) -> Dict:
        """Create error event for failed API calls"""
        return {
            'event_id': f"{city['id']}_{int(time.time())}_error",
            'city_id': city['id'],
            'city_name': city['name'],
            'county': city['county'],
            'country': 'Romania',
            'latitude': city['lat'],
            'longitude': city['lon'],
            'elevation': city['elevation'],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data_source': 'open-meteo-comprehensive',
            'raw_data': None,
            'collection_status': 'error',
            'error_message': error_message,
            'data_richness_score': 0.0,
            'geographic_zone': self._classify_geographic_zone(city),
            'climate_zone': self._classify_climate_zone(city)
        }

    def _save_to_csv(self, weather_event: Dict):
        """Save weather event data to multiple CSV files"""
        try:
            # Save summary data
            summary_row = [
                weather_event['event_id'],
                weather_event['city_id'],
                weather_event['city_name'],
                weather_event['county'],
                weather_event['country'],
                weather_event['latitude'],
                weather_event['longitude'],
                weather_event['elevation'],
                weather_event['timestamp'],
                weather_event['collection_status'],
                weather_event['data_richness_score'],
                weather_event['geographic_zone'],
                weather_event['climate_zone'],
                weather_event.get('error_message', '')
            ]
            
            with open(self.csv_files['summary'], 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(summary_row)
            
            # If we have successful data, save detailed weather information
            if weather_event['collection_status'] == 'success' and weather_event['raw_data']:
                raw_data = weather_event['raw_data']
                
                # Save current weather data
                if 'current' in raw_data:
                    current = raw_data['current']
                    current_row = [
                        weather_event['event_id'],
                        weather_event['city_id'],
                        weather_event['timestamp'],
                        current.get('temperature_2m'),
                        current.get('relative_humidity_2m'),
                        current.get('apparent_temperature'),
                        current.get('is_day'),
                        current.get('precipitation'),
                        current.get('rain'),
                        current.get('showers'),
                        current.get('snowfall'),
                        current.get('weather_code'),
                        current.get('cloud_cover'),
                        current.get('surface_pressure'),
                        current.get('sea_level_pressure'),
                        current.get('wind_speed_10m'),
                        current.get('wind_direction_10m'),
                        current.get('wind_gusts_10m')
                    ]
                    
                    with open(self.csv_files['current'], 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(current_row)
                
                # Save hourly data
                if 'hourly' in raw_data and 'time' in raw_data['hourly']:
                    hourly_data = raw_data['hourly']
                    time_points = hourly_data['time']
                    
                    for i, time_point in enumerate(time_points):
                        hourly_row = [
                            weather_event['event_id'],
                            weather_event['city_id'],
                            weather_event['timestamp'],
                            time_point,
                            hourly_data.get('temperature_2m', [None] * len(time_points))[i],
                            hourly_data.get('relative_humidity_2m', [None] * len(time_points))[i],
                            hourly_data.get('dew_point_2m', [None] * len(time_points))[i],
                            hourly_data.get('apparent_temperature', [None] * len(time_points))[i],
                            hourly_data.get('pressure_msl', [None] * len(time_points))[i],
                            hourly_data.get('surface_pressure', [None] * len(time_points))[i],
                            hourly_data.get('cloud_cover', [None] * len(time_points))[i],
                            hourly_data.get('visibility', [None] * len(time_points))[i],
                            hourly_data.get('wind_speed_10m', [None] * len(time_points))[i],
                            hourly_data.get('wind_direction_10m', [None] * len(time_points))[i],
                            hourly_data.get('wind_gusts_10m', [None] * len(time_points))[i],
                            hourly_data.get('precipitation', [None] * len(time_points))[i],
                            hourly_data.get('rain', [None] * len(time_points))[i],
                            hourly_data.get('showers', [None] * len(time_points))[i],
                            hourly_data.get('snowfall', [None] * len(time_points))[i],
                            hourly_data.get('weather_code', [None] * len(time_points))[i],
                            hourly_data.get('shortwave_radiation', [None] * len(time_points))[i],
                            hourly_data.get('uv_index', [None] * len(time_points))[i],
                            hourly_data.get('soil_temperature_0cm', [None] * len(time_points))[i],
                            hourly_data.get('soil_moisture_0_1cm', [None] * len(time_points))[i]
                        ]
                        
                        with open(self.csv_files['hourly'], 'a', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow(hourly_row)
                
                # Save daily data
                if 'daily' in raw_data and 'time' in raw_data['daily']:
                    daily_data = raw_data['daily']
                    time_points = daily_data['time']
                    
                    for i, date_point in enumerate(time_points):
                        daily_row = [
                            weather_event['event_id'],
                            weather_event['city_id'],
                            weather_event['timestamp'],
                            date_point,
                            daily_data.get('weather_code', [None] * len(time_points))[i],
                            daily_data.get('temperature_2m_max', [None] * len(time_points))[i],
                            daily_data.get('temperature_2m_min', [None] * len(time_points))[i],
                            daily_data.get('apparent_temperature_max', [None] * len(time_points))[i],
                            daily_data.get('apparent_temperature_min', [None] * len(time_points))[i],
                            daily_data.get('sunrise', [None] * len(time_points))[i],
                            daily_data.get('sunset', [None] * len(time_points))[i],
                            daily_data.get('precipitation_sum', [None] * len(time_points))[i],
                            daily_data.get('rain_sum', [None] * len(time_points))[i],
                            daily_data.get('snowfall_sum', [None] * len(time_points))[i],
                            daily_data.get('wind_speed_10m_max', [None] * len(time_points))[i],
                            daily_data.get('wind_gusts_10m_max', [None] * len(time_points))[i]
                        ]
                        
                        with open(self.csv_files['daily'], 'a', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow(daily_row)
            
            # Update metadata
            metadata_row = [
                weather_event['city_id'],
                weather_event['city_name'],
                weather_event['county'],
                weather_event['country'],
                weather_event['latitude'],
                weather_event['longitude'],
                weather_event['elevation'],
                weather_event['geographic_zone'],
                weather_event['climate_zone'],
                weather_event['timestamp']
            ]
            
            # For metadata, we'll update existing entries
            self._update_metadata_csv(metadata_row)
            
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")

    def _update_metadata_csv(self, metadata_row):
        """Update metadata CSV, replacing existing city entries"""
        try:
            # Read existing metadata
            metadata_df = pd.DataFrame()
            if self.csv_files['metadata'].exists():
                try:
                    metadata_df = pd.read_csv(self.csv_files['metadata'])
                except pd.errors.EmptyDataError:
                    pass
            
            # Create new row DataFrame
            new_row_df = pd.DataFrame([metadata_row], columns=[
                'city_id', 'city_name', 'county', 'country', 'latitude', 'longitude',
                'elevation', 'geographic_zone', 'climate_zone', 'last_updated'
            ])
            
            # Remove existing entry for this city_id if it exists
            if not metadata_df.empty:
                metadata_df = metadata_df[metadata_df['city_id'] != metadata_row[0]]
            
            # Add new row
            metadata_df = pd.concat([metadata_df, new_row_df], ignore_index=True)
            
            # Save back to CSV
            metadata_df.to_csv(self.csv_files['metadata'], index=False)
            
        except Exception as e:
            logger.error(f"Error updating metadata CSV: {e}")

    async def collect_all_comprehensive_data(self):
        """Collect comprehensive weather data for all Romanian cities and save to CSV"""
        logger.info(f"Starting comprehensive weather data collection for {len(self.cities)} Romanian cities")
        
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_comprehensive_weather_data(session, city) for city in self.cities]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful_events = 0
            failed_events = 0
            total_richness = 0.0
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Task failed with exception: {result}")
                    failed_events += 1
                    continue
                
                try:
                    # Save to CSV
                    self._save_to_csv(result)
                    
                    if result['collection_status'] == 'success':
                        successful_events += 1
                        total_richness += result['data_richness_score']
                    else:
                        failed_events += 1
                        
                except Exception as e:
                    logger.error(f"Failed to save event to CSV: {e}")
                    failed_events += 1
            
            avg_richness = total_richness / successful_events if successful_events > 0 else 0
            logger.info(f"Comprehensive collection completed. Success: {successful_events}, Failed: {failed_events}")
            logger.info(f"Average data richness score: {avg_richness:.3f}")
            logger.info(f"Data saved to: {self.output_dir}")

    def run_collection(self):
        """Run comprehensive weather data collection"""
        try:
            asyncio.run(self.collect_all_comprehensive_data())
        except Exception as e:
            logger.error(f"Collection failed: {e}")

    def start_scheduler(self):
        """Start the comprehensive weather data collection scheduler"""
        logger.info("Starting comprehensive weather data collection scheduler")
        
        # Schedule collection every 30 minutes for CSV storage (less frequent than Kafka)
        schedule.every(30).minutes.do(self.run_collection)
        
        # Run initial collection
        logger.info("Running initial comprehensive collection...")
        self.run_collection()
        
        # Keep scheduler running
        while True:
            schedule.run_pending()
            time.sleep(60)

    def run_single_collection(self):
        """Run a single collection cycle (useful for testing)"""
        logger.info("Running single weather data collection...")
        self.run_collection()
        logger.info(f"Collection complete. Data saved to: {self.output_dir}")

    def get_data_summary(self):
        """Get summary of collected data"""
        try:
            summary_stats = {}
            
            for file_type, file_path in self.csv_files.items():
                if file_path.exists():
                    df = pd.read_csv(file_path)
                    summary_stats[file_type] = {
                        'total_records': len(df),
                        'file_size_mb': round(file_path.stat().st_size / (1024*1024), 2),
                        'last_modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                    }
                    
                    if file_type == 'summary':
                        summary_stats[file_type]['success_rate'] = round(
                            (df['collection_status'] == 'success').sum() / len(df) * 100, 1
                        ) if len(df) > 0 else 0
                        summary_stats[file_type]['avg_richness'] = round(
                            df['data_richness_score'].mean(), 3
                        ) if len(df) > 0 else 0
                else:
                    summary_stats[file_type] = {'status': 'not_created'}
            
            return summary_stats
        except Exception as e:
            logger.error(f"Error getting data summary: {e}")
            return {}

    def cleanup_old_data(self, days_to_keep: int = 7):
        """Clean up old data from CSV files"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            for file_type, file_path in self.csv_files.items():
                if file_path.exists() and file_type != 'metadata':  # Keep all metadata
                    df = pd.read_csv(file_path)
                    
                    # Determine date column based on file type
                    if file_type == 'summary' or file_type == 'current':
                        date_col = 'timestamp'
                    elif file_type == 'hourly':
                        date_col = 'collection_timestamp'
                    elif file_type == 'daily':
                        date_col = 'collection_timestamp'
                    else:
                        continue
                    
                    if date_col in df.columns:
                        # Convert to datetime and filter
                        df[date_col] = pd.to_datetime(df[date_col])
                        filtered_df = df[df[date_col] >= cutoff_date]
                        
                        # Save filtered data back
                        filtered_df.to_csv(file_path, index=False)
                        
                        removed_count = len(df) - len(filtered_df)
                        if removed_count > 0:
                            logger.info(f"Cleaned up {removed_count} old records from {file_type}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


def main():
    """Main function to run the weather producer"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced Weather Data Producer - CSV Output')
    parser.add_argument('--mode', choices=['single', 'schedule', 'summary', 'cleanup'], 
                       default='single', help='Operation mode')
    parser.add_argument('--output-dir', default='./weather_data', 
                       help='Output directory for CSV files')
    parser.add_argument('--cleanup-days', type=int, default=7, 
                       help='Days of data to keep during cleanup')
    
    args = parser.parse_args()
    
    # Set output directory from argument
    os.environ['OUTPUT_DIR'] = args.output_dir
    
    producer = EnhancedWeatherProducerCSV()
    
    try:
        if args.mode == 'single':
            producer.run_single_collection()
            
        elif args.mode == 'schedule':
            producer.start_scheduler()
            
        elif args.mode == 'summary':
            summary = producer.get_data_summary()
            print("\n=== Weather Data Summary ===")
            for file_type, stats in summary.items():
                print(f"\n{file_type.upper()}:")
                if 'status' in stats:
                    print(f"  Status: {stats['status']}")
                else:
                    print(f"  Records: {stats['total_records']}")
                    print(f"  Size: {stats['file_size_mb']} MB")
                    print(f"  Last Modified: {stats['last_modified']}")
                    if 'success_rate' in stats:
                        print(f"  Success Rate: {stats['success_rate']}%")
                        print(f"  Avg Richness: {stats['avg_richness']}")
            
        elif args.mode == 'cleanup':
            producer.cleanup_old_data(args.cleanup_days)
            print(f"Cleanup completed - kept last {args.cleanup_days} days of data")
            
    except KeyboardInterrupt:
        logger.info("Shutting down weather producer")
    except Exception as e:
        logger.error(f"Application error: {e}")


if __name__ == "__main__":
    main()
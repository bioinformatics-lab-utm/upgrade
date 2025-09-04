#!/usr/bin/env python3
"""
Simple APRS.fi weather data collector - Fixed version
"""

import requests
import json
import time
from datetime import datetime, timezone
import csv
import os

class APRSWeatherTester:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://api.aprs.fi/api/get'

    def get_weather_stations_simple(self):
        """Get weather stations with simpler approach"""
        # Try different API endpoints and methods
        methods_to_try = [
            # Method 1: Get weather stations only
            {
                'name': '*',
                'what': 'wx',
                'apikey': self.api_key,
                'format': 'json'
            },
            # Method 2: Get all locations first
            {
                'name': '*',
                'what': 'loc',
                'apikey': self.api_key,
                'format': 'json'
            },
            # Method 3: Try specific callsigns
            {
                'name': 'W*',
                'apikey': self.api_key,
                'format': 'json'
            }
        ]
        
        for i, params in enumerate(methods_to_try, 1):
            try:
                print(f"Trying method {i}: {params.get('what', 'all')}")
                response = requests.get(self.base_url, params=params, timeout=60)
                
                print(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"API result: {data.get('result', 'unknown')}")
                    
                    if data.get('result') == 'ok' and 'entries' in data:
                        entries = data['entries']
                        print(f"Found {len(entries)} entries")
                        
                        # Filter for weather stations
                        weather_stations = []
                        for entry in entries:
                            if entry.get('weather'):
                                weather_stations.append(entry)
                        
                        print(f"Weather stations: {len(weather_stations)}")
                        if weather_stations:
                            return weather_stations
                    else:
                        print(f"API response: {data}")
                else:
                    print(f"HTTP Error: {response.status_code}")
                    print(f"Response: {response.text[:200]}...")
                    
            except requests.exceptions.Timeout:
                print(f"Method {i}: Timeout")
            except Exception as e:
                print(f"Method {i}: Error - {e}")
        
        return []

    def fahrenheit_to_celsius(self, temp_f):
        """Convert Fahrenheit to Celsius"""
        try:
            return round((float(temp_f) - 32) * 5/9, 1)
        except (ValueError, TypeError):
            return None

    def parse_weather_data(self, station):
        """Parse APRS weather data into readable format"""
        weather = station.get('weather', {})
        if not weather:
            return None
        
        last_time = int(station.get('lasttime', 0))
        hours_ago = (time.time() - last_time) / 3600 if last_time else 999
        
        parsed_data = {
            'station_id': station.get('name', 'Unknown'),
            'latitude': float(station.get('lat', 0)),
            'longitude': float(station.get('lng', 0)),
            'last_update': datetime.fromtimestamp(last_time).strftime('%Y-%m-%d %H:%M:%S') if last_time else 'Unknown',
            'hours_ago': round(hours_ago, 1),
            'comment': station.get('comment', ''),
            
            # Weather data
            'temperature_c': self.fahrenheit_to_celsius(weather.get('temp')),
            'temperature_f': weather.get('temp'),
            'humidity_percent': weather.get('humidity'),
            'pressure_inhg': weather.get('pressure'),
            'pressure_hpa': round(float(weather['pressure']) * 33.8639, 1) if weather.get('pressure') else None,
            'wind_speed_mph': weather.get('wind_speed'),
            'wind_speed_kmh': round(float(weather['wind_speed']) * 1.60934, 1) if weather.get('wind_speed') else None,
            'wind_direction': weather.get('wind_direction'),
            'wind_gust_mph': weather.get('wind_gust'),
            'rain_1h_inch': weather.get('rain_1h'),
            'rain_1h_mm': round(float(weather['rain_1h']) * 25.4, 1) if weather.get('rain_1h') else None,
            'rain_24h_inch': weather.get('rain_24h'),
            'rain_24h_mm': round(float(weather['rain_24h']) * 25.4, 1) if weather.get('rain_24h') else None,
        }
        
        return parsed_data

    def display_station_summary(self, stations_data):
        """Display summary of collected stations"""
        if not stations_data:
            print("No weather stations found!")
            return
        
        print(f"\n=== APRS Weather Stations Summary ===")
        print(f"Total stations: {len(stations_data)}")
        
        # Sort by data freshness
        sorted_stations = sorted(stations_data, key=lambda x: x['hours_ago'])
        
        print("\nRecent stations (last 24 hours):")
        recent_count = 0
        for station in sorted_stations:
            if station['hours_ago'] <= 24:
                recent_count += 1
                temp_info = f"{station['temperature_c']}°C" if station['temperature_c'] else "No temp"
                humidity_info = f"{station['humidity_percent']}%" if station['humidity_percent'] else "No humidity"
                location = f"({station['latitude']:.2f}, {station['longitude']:.2f})"
                
                print(f"  {station['station_id']:10s} | {temp_info:8s} | {humidity_info:10s} | "
                      f"{station['hours_ago']:4.1f}h ago | {location}")
        
        print(f"\nStations with recent data (last 24h): {recent_count}")

    def display_detailed_station(self, station_data):
        """Display detailed information for a single station"""
        print(f"\n=== Detailed Station Info: {station_data['station_id']} ===")
        
        for key, value in station_data.items():
            if value is not None:
                print(f"{key:20s}: {value}")

    def save_to_csv(self, stations_data, filename='aprs_weather_data.csv'):
        """Save data to CSV file"""
        if not stations_data:
            print("No data to save!")
            return
        
        fieldnames = list(stations_data[0].keys())
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(stations_data)
        
        print(f"\nData saved to {filename}")

    def run_test(self):
        """Main test function"""
        print("Starting APRS.fi weather data test...")
        print("=" * 50)
        
        # Fetch weather stations with multiple methods
        all_stations = self.get_weather_stations_simple()
        print(f"Total stations fetched: {len(all_stations)}")
        
        if not all_stations:
            print("No stations found. Try:")
            print("1. Register at aprs.fi for a real API key")
            print("2. Check internet connection")
            print("3. Try again later")
            return
        
        # Parse all weather stations
        weather_stations = []
        for station in all_stations:
            parsed = self.parse_weather_data(station)
            if parsed:
                weather_stations.append(parsed)
        
        print(f"Stations with weather data: {len(weather_stations)}")
        
        # Display results
        self.display_station_summary(weather_stations)
        
        # Show detailed info for first few stations
        if weather_stations:
            print(f"\n=== Sample Detailed Station Data ===")
            for i, station in enumerate(weather_stations[:3]):
                self.display_detailed_station(station)
                if i < 2:
                    print("-" * 50)
        
        # Save to CSV
        self.save_to_csv(weather_stations)
        
        print(f"\n=== Test Complete ===")
        print(f"Found {len(weather_stations)} weather stations total")


def main():
    print("APRS.fi Weather Data Tester")
    print("Get API key from: https://aprs.fi/ -> My Account")
    
    API_KEY = input("Enter your APRS.fi API key: ").strip()
    
    if not API_KEY:
        print("API key required!")
        return
    
    tester = APRSWeatherTester(API_KEY)
    tester.run_test()


if __name__ == "__main__":
    main()
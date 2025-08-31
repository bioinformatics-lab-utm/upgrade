# data/weather_loader.py
import requests
import psycopg2
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict

class WeatherLoader:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'weather_db'),
            'user': os.getenv('DB_USER', 'metabase'),
            'password': os.getenv('DB_PASS', 'weather_pass_2024'),
            'port': os.getenv('DB_PORT', '5432')
        }
        
        # Координаты основных городов
        self.cities = {
            'Romania': [
                {'name': 'Suceava', 'lat': 47.6635, 'lon': 26.2535},
                {'name': 'Bucharest', 'lat': 44.4268, 'lon': 26.1025},
                {'name': 'Cluj-Napoca', 'lat': 46.7712, 'lon': 23.6236},
                {'name': 'Timisoara', 'lat': 45.7489, 'lon': 21.2087},
                {'name': 'Constanta', 'lat': 44.1598, 'lon': 28.6348},
                {'name': 'Iasi', 'lat': 47.1585, 'lon': 27.6014},
                {'name': 'Brasov', 'lat': 45.6427, 'lon': 25.5887},
                {'name': 'Craiova', 'lat': 44.3302, 'lon': 23.7949},
            ],
            'Moldova': [
                {'name': 'Chisinau', 'lat': 47.0105, 'lon': 28.8638},
                {'name': 'Balti', 'lat': 47.7613, 'lon': 27.9289},
                {'name': 'Cahul', 'lat': 45.9075, 'lon': 28.1984},
                {'name': 'Soroca', 'lat': 48.1581, 'lon': 28.2956},
                {'name': 'Orhei', 'lat': 47.3697, 'lon': 28.8219},
                {'name': 'Ungheni', 'lat': 47.2086, 'lon': 27.7976},
            ]
        }

    def get_connection(self):
        """Подключение к PostgreSQL"""
        return psycopg2.connect(**self.db_config)

    def fetch_weather_openmeteo(self, lat: float, lon: float, days: int = 7) -> Dict:
        """
        Получение данных погоды из Open-Meteo API (бесплатный)
        """
        url = "https://api.open-meteo.com/v1/forecast"
        
        params = {
            'latitude': lat,
            'longitude': lon,
            'hourly': 'temperature_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m,wind_direction_10m',
            'past_days': days,
            'forecast_days': 1,
            'timezone': 'Europe/Bucharest'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Ошибка API запроса для {lat}, {lon}: {e}")
            return None

    def process_weather_data(self, data: Dict, country: str, city: str, lat: float, lon: float) -> List[Dict]:
        """Обработка данных API в формат для БД"""
        if not data or 'hourly' not in data:
            return []
        
        hourly = data['hourly']
        processed_data = []
        
        for i, timestamp in enumerate(hourly['time']):
            dt = datetime.fromisoformat(timestamp.replace('T', ' '))
            
            weather_point = {
                'country': country,
                'region': f"{city} Region",
                'city': city,
                'latitude': lat,
                'longitude': lon,
                'date': dt.date(),
                'hour': dt.hour,
                'temperature': hourly['temperature_2m'][i],
                'humidity': hourly['relative_humidity_2m'][i],
                'precipitation': hourly['precipitation'][i],
                'pressure': hourly['surface_pressure'][i],
                'wind_speed': hourly['wind_speed_10m'][i],
                'wind_direction': hourly['wind_direction_10m'][i]
            }
            processed_data.append(weather_point)
        
        return processed_data

    def insert_weather_data(self, weather_records: List[Dict]):
        """Вставка данных в PostgreSQL"""
        if not weather_records:
            return
        
        conn = self.get_connection()
        cur = conn.cursor()
        
        try:
            # Очистка старых данных (старше 30 дней)
            cur.execute("""
                DELETE FROM weather_data 
                WHERE date < CURRENT_DATE - INTERVAL '30 days'
            """)
            
            # Вставка новых данных
            insert_query = """
                INSERT INTO weather_data 
                (country, region, city, latitude, longitude, date, hour, 
                 temperature, humidity, precipitation, pressure, wind_speed, wind_direction)
                VALUES (%(country)s, %(region)s, %(city)s, %(latitude)s, %(longitude)s, 
                        %(date)s, %(hour)s, %(temperature)s, %(humidity)s, %(precipitation)s,
                        %(pressure)s, %(wind_speed)s, %(wind_direction)s)
                ON CONFLICT DO NOTHING
            """
            
            cur.executemany(insert_query, weather_records)
            conn.commit()
            
            print(f"Вставлено {cur.rowcount} записей в БД")
            
        except Exception as e:
            print(f"Ошибка вставки данных: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    def load_all_weather_data(self, days: int = 7):
        """Загрузка данных для всех городов"""
        all_records = []
        
        for country, cities in self.cities.items():
            print(f"Загрузка данных для {country}...")
            
            for city_info in cities:
                print(f"  Обработка {city_info['name']}...")
                
                # Получение данных из API
                weather_data = self.fetch_weather_openmeteo(
                    city_info['lat'], 
                    city_info['lon'], 
                    days
                )
                
                if weather_data:
                    # Обработка и добавление к общему списку
                    processed = self.process_weather_data(
                        weather_data, 
                        country, 
                        city_info['name'],
                        city_info['lat'], 
                        city_info['lon']
                    )
                    all_records.extend(processed)
                
                # Пауза между запросами
                time.sleep(1)
        
        # Вставка всех данных
        print(f"Вставка {len(all_records)} записей в базу данных...")
        self.insert_weather_data(all_records)
        print("Загрузка завершена!")

    def generate_sample_data(self):
        """Генерация тестовых данных для демонстрации"""
        import random
        from datetime import date, timedelta
        
        sample_data = []
        
        # Генерируем данные за последние 30 дней
        for i in range(30):
            current_date = date.today() - timedelta(days=i)
            
            for country, cities in self.cities.items():
                for city_info in cities:
                    # Генерируем реалистичные данные для региона
                    base_temp = 15 if country == 'Moldova' else 18
                    temp_variation = random.uniform(-5, 10)
                    
                    sample_record = {
                        'country': country,
                        'region': f"{city_info['name']} Region",
                        'city': city_info['name'],
                        'latitude': city_info['lat'],
                        'longitude': city_info['lon'],
                        'date': current_date,
                        'hour': random.randint(0, 23),
                        'temperature': round(base_temp + temp_variation, 1),
                        'humidity': round(random.uniform(40, 85), 1),
                        'precipitation': round(random.exponential(1.5), 1),
                        'pressure': round(random.uniform(1000, 1025), 1),
                        'wind_speed': round(random.uniform(0, 15), 1),
                        'wind_direction': random.randint(0, 360)
                    }
                    sample_data.append(sample_record)
        
        self.insert_weather_data(sample_data)
        print(f"Сгенерировано {len(sample_data)} тестовых записей")


def main():
    loader = WeatherLoader()
    
    # Проверяем аргументы командной строки
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--sample':
        print("Генерация тестовых данных...")
        loader.generate_sample_data()
    else:
        print("Загрузка реальных метеоданных...")
        loader.load_all_weather_data(days=7)

if __name__ == "__main__":
    main()
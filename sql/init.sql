-- sql/init.sql
-- Инициализация базы данных для метеоданных

-- Включаем расширение PostGIS для работы с геоданными
CREATE EXTENSION IF NOT EXISTS postgis;

-- Основная таблица метеоданных
CREATE TABLE weather_data (
    id SERIAL PRIMARY KEY,
    country VARCHAR(50) NOT NULL,
    region VARCHAR(100),
    city VARCHAR(100),
    latitude DECIMAL(10,8) NOT NULL,
    longitude DECIMAL(11,8) NOT NULL,
    date DATE NOT NULL,
    hour INTEGER CHECK (hour >= 0 AND hour <= 23),
    temperature DECIMAL(5,2),          -- температура в °C
    humidity DECIMAL(5,2),             -- влажность в %
    precipitation DECIMAL(6,2),        -- осадки в мм
    pressure DECIMAL(7,2),             -- давление в hPa
    wind_speed DECIMAL(5,2),           -- скорость ветра м/с
    wind_direction INTEGER,            -- направление ветра в градусах
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Геометрическая колонка для пространственных запросов
ALTER TABLE weather_data 
ADD COLUMN geom GEOMETRY(POINT, 4326);

-- Обновление геометрии при вставке/обновлении
CREATE OR REPLACE FUNCTION update_geom()
RETURNS TRIGGER AS $$
BEGIN
    NEW.geom = ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER weather_geom_trigger
    BEFORE INSERT OR UPDATE ON weather_data
    FOR EACH ROW EXECUTE FUNCTION update_geom();

-- Индексы для производительности
CREATE INDEX idx_weather_country_date ON weather_data(country, date);
CREATE INDEX idx_weather_coords ON weather_data(latitude, longitude);
CREATE INDEX idx_weather_geom ON weather_data USING GIST(geom);
CREATE INDEX idx_weather_date_desc ON weather_data(date DESC);

-- Вставка тестовых городов Румынии и Молдовы
INSERT INTO weather_data (country, region, city, latitude, longitude, date, temperature, humidity, precipitation) VALUES
-- Румыния
('Romania', 'Suceava County', 'Suceava', 47.6635, 26.2535, CURRENT_DATE - INTERVAL '1 day', 18.5, 65.0, 2.5),
('Romania', 'Bucuresti', 'Bucharest', 44.4268, 26.1025, CURRENT_DATE - INTERVAL '1 day', 22.0, 58.0, 0.0),
('Romania', 'Cluj County', 'Cluj-Napoca', 46.7712, 23.6236, CURRENT_DATE - INTERVAL '1 day', 19.5, 62.0, 1.2),
('Romania', 'Timis County', 'Timisoara', 45.7489, 21.2087, CURRENT_DATE - INTERVAL '1 day', 21.0, 55.0, 0.5),
('Romania', 'Constanta County', 'Constanta', 44.1598, 28.6348, CURRENT_DATE - INTERVAL '1 day', 20.5, 70.0, 0.0),

-- Молдова
('Moldova', 'Chisinau Municipality', 'Chisinau', 47.0105, 28.8638, CURRENT_DATE - INTERVAL '1 day', 19.0, 68.0, 3.0),
('Moldova', 'Balti Municipality', 'Balti', 47.7613, 27.9289, CURRENT_DATE - INTERVAL '1 day', 17.5, 72.0, 5.2),
('Moldova', 'Cahul District', 'Cahul', 45.9075, 28.1984, CURRENT_DATE - INTERVAL '1 day', 20.0, 60.0, 1.0),
('Moldova', 'Soroca District', 'Soroca', 48.1581, 28.2956, CURRENT_DATE - INTERVAL '1 day', 16.5, 75.0, 4.5),
('Moldova', 'Orhei District', 'Orhei', 47.3697, 28.8219, CURRENT_DATE - INTERVAL '1 day', 18.0, 70.0, 2.8);

-- Представление для агрегированных данных по странам
CREATE VIEW weather_summary AS
SELECT 
    country,
    date,
    AVG(temperature) as avg_temperature,
    AVG(humidity) as avg_humidity,
    AVG(precipitation) as avg_precipitation,
    MIN(temperature) as min_temperature,
    MAX(temperature) as max_temperature,
    COUNT(*) as measurement_count
FROM weather_data 
GROUP BY country, date
ORDER BY date DESC;

-- Представление для density plot данных
CREATE VIEW weather_density_data AS
SELECT 
    country,
    ROUND(temperature::numeric, 1) as temp_rounded,
    ROUND(humidity::numeric, 1) as humidity_rounded,
    ROUND(precipitation::numeric, 1) as precip_rounded,
    COUNT(*) as frequency
FROM weather_data 
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY country, temp_rounded, humidity_rounded, precip_rounded
ORDER BY country, temp_rounded;
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './WeatherDashboard.css';

const WeatherDashboard = () => {
  const [weather, setWeather] = useState(null);
  const [forecast, setForecast] = useState([]);
  const [location, setLocation] = useState({ lat: 44.4268, lon: 26.1025, name: 'Bucharest, Romania' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadWeatherData();
    const interval = setInterval(loadWeatherData, 10 * 60 * 1000); // Update every 10 minutes
    return () => clearInterval(interval);
  }, [location]);

  const loadWeatherData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Call Open-Meteo API directly
      const response = await axios.get(`http://localhost:8080/v1/forecast`, {
        params: {
          latitude: location.lat,
          longitude: location.lon,
          current_weather: true,
          hourly: 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
          daily: 'temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max',
          timezone: 'Europe/Bucharest',
          forecast_days: 7
        }
      });

      setWeather(response.data.current_weather);
      
      // Process daily forecast
      if (response.data.daily) {
        const days = response.data.daily.time.map((date, index) => ({
          date,
          temp_max: response.data.daily.temperature_2m_max[index],
          temp_min: response.data.daily.temperature_2m_min[index],
          precipitation: response.data.daily.precipitation_sum[index],
          wind_speed: response.data.daily.wind_speed_10m_max[index]
        }));
        setForecast(days);
      }

    } catch (err) {
      console.error('Error loading weather data:', err);
      setError('Failed to load weather data. Make sure Open-Meteo API is running on port 8080.');
    } finally {
      setLoading(false);
    }
  };

  const getWeatherIcon = (temperature, windSpeed) => {
    if (temperature > 25) return '☀️';
    if (temperature < 5) return '❄️';
    if (windSpeed > 20) return '💨';
    return '⛅';
  };

  const locations = [
    { lat: 44.4268, lon: 26.1025, name: 'Bucharest, Romania' },
    { lat: 46.7712, lon: 23.6236, name: 'Cluj-Napoca, Romania' },
    { lat: 45.7489, lon: 21.2087, name: 'Timișoara, Romania' },
    { lat: 47.1585, lon: 27.6014, name: 'Iași, Romania' },
    { lat: 44.1598, lon: 28.6348, name: 'Constanța, Romania' }
  ];

  if (loading && !weather) {
    return (
      <div className="weather-dashboard">
        <div className="loading">
          <div className="spinner"></div>
          <p>Loading weather data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="weather-dashboard">
        <div className="alert alert-danger">
          <strong>Error:</strong> {error}
          <button className="btn btn-sm" onClick={loadWeatherData} style={{marginLeft: '10px'}}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="weather-dashboard">
      <div className="weather-header">
        <div className="location-selector">
          <label>Location:</label>
          <select 
            value={`${location.lat},${location.lon}`}
            onChange={(e) => {
              const [lat, lon] = e.target.value.split(',');
              const loc = locations.find(l => l.lat === parseFloat(lat) && l.lon === parseFloat(lon));
              setLocation(loc);
            }}
          >
            {locations.map(loc => (
              <option key={`${loc.lat},${loc.lon}`} value={`${loc.lat},${loc.lon}`}>
                {loc.name}
              </option>
            ))}
          </select>
        </div>
        <button className="btn-primary" onClick={loadWeatherData}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Refresh
        </button>
      </div>

      <div className="weather-grid">
        {/* Current Weather Card */}
        <div className="card weather-current">
          <div className="card-header">
            <h3>Current Weather</h3>
            <span className="location-name">{location.name}</span>
          </div>
          <div className="card-body">
            {weather && (
              <div className="current-weather">
                <div className="weather-icon-large">
                  {getWeatherIcon(weather.temperature, weather.windspeed)}
                </div>
                <div className="weather-temp">
                  <span className="temp-value">{weather.temperature.toFixed(1)}</span>
                  <span className="temp-unit">°C</span>
                </div>
                <div className="weather-details">
                  <div className="weather-detail">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span>{weather.windspeed.toFixed(1)} km/h</span>
                  </div>
                  <div className="weather-detail">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span>{weather.winddirection}°</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 7-Day Forecast */}
        <div className="card weather-forecast">
          <div className="card-header">
            <h3>7-Day Forecast</h3>
          </div>
          <div className="card-body">
            <div className="forecast-grid">
              {forecast.map((day, index) => (
                <div key={index} className="forecast-day">
                  <div className="forecast-date">
                    {index === 0 ? 'Today' : new Date(day.date).toLocaleDateString('en-US', { weekday: 'short' })}
                  </div>
                  <div className="forecast-icon">
                    {getWeatherIcon(day.temp_max, day.wind_speed)}
                  </div>
                  <div className="forecast-temps">
                    <span className="temp-max">{day.temp_max.toFixed(0)}°</span>
                    <span className="temp-min">{day.temp_min.toFixed(0)}°</span>
                  </div>
                  <div className="forecast-precip">
                    {day.precipitation > 0 ? (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                        {day.precipitation.toFixed(1)}mm
                      </>
                    ) : (
                      <span style={{opacity: 0.5}}>No rain</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Info Note */}
      <div className="weather-footer">
        <p className="text-muted">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{verticalAlign: 'middle', marginRight: '5px'}}>
            <circle cx="12" cy="12" r="10" strokeWidth="2"/>
            <line x1="12" y1="16" x2="12" y2="12" strokeWidth="2" strokeLinecap="round"/>
            <line x1="12" y1="8" x2="12.01" y2="8" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          Weather data provided by Open-Meteo API. Updates every 10 minutes.
        </p>
      </div>
    </div>
  );
};

export default WeatherDashboard;

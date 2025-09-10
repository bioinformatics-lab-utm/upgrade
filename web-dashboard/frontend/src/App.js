import React, { useState, useEffect, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, CircleMarker } from 'react-leaflet';
import L from 'leaflet';
import axios from 'axios';
import './App.css'; // Импортируем CSS

// Fix for default markers in react-leaflet
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const API_BASE = 'http://localhost:8000/api';

function App() {
  const [weatherData, setWeatherData] = useState([]);
  const [locations, setLocations] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedCity, setSelectedCity] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [error, setError] = useState(null);

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [weatherRes, locationsRes, statsRes] = await Promise.all([
        axios.get(`${API_BASE}/weather/latest`),
        axios.get(`${API_BASE}/locations`),
        axios.get(`${API_BASE}/weather/stats`)
      ]);
      
      if (weatherRes.data.success) {
        setWeatherData(weatherRes.data.data);
      }
      if (locationsRes.data.success) {
        setLocations(locationsRes.data.data);
      }
      if (statsRes.data.success) {
        setStats(statsRes.data.data);
      }
      
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Error loading data:', error);
      setError('Failed to load data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 300000); // Refresh every 5 minutes
    return () => clearInterval(interval);
  }, [loadData]);

  const getTemperatureColor = (temp) => {
    if (temp < 0) return '#0066cc';
    if (temp < 10) return '#0099ff';
    if (temp < 20) return '#00cc00';
    if (temp < 30) return '#ffcc00';
    return '#ff6600';
  };

  const formatDateTime = (dateString) => {
    return new Date(dateString).toLocaleString();
  };

  const formatNumber = (num) => {
    return num != null ? Number(num).toFixed(1) : 'N/A';
  };

  if (loading) {
    return (
      <div className="app">
        <div className="header">
          <h1>UPGRADE - Environmental Genomic Surveillance</h1>
        </div>
        <div className="loading">Loading data...</div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="header">
        <h1>UPGRADE - Environmental Genomic Surveillance</h1>
        <p>Real-time environmental monitoring across Romania and Moldova</p>
      </div>
      
      <div className="main-content">
        <div className="sidebar">
          <h3>System Statistics</h3>
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-value">{locations.length}</div>
              <div className="stat-label">Locations</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{stats.total_measurements || 0}</div>
              <div className="stat-label">Total Measurements</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{formatNumber(stats.avg_temperature)}°C</div>
              <div className="stat-label">Avg Temperature</div>
            </div>
            <div className="stat-card">
              <div className="stat-value">{formatNumber(stats.avg_humidity)}%</div>
              <div className="stat-label">Avg Humidity</div>
            </div>
          </div>

          <h3>Current Weather</h3>
          {error && <div style={{color: 'red', marginBottom: '1rem'}}>{error}</div>}
          <div className="city-list">
            {weatherData.map((weather, index) => (
              <div 
                key={index} 
                className="city-item"
                style={{ 
                  cursor: 'pointer',
                  backgroundColor: selectedCity === weather.city ? '#e8f4f8' : 'transparent'
                }}
                onClick={() => setSelectedCity(weather.city)}
              >
                <div>
                  <strong>{weather.city}</strong>
                  <div style={{ fontSize: '0.8rem', color: '#666' }}>
                    {weather.country}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ 
                    color: getTemperatureColor(weather.temperature),
                    fontWeight: 'bold'
                  }}>
                    {formatNumber(weather.temperature)}°C
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#666' }}>
                    {formatNumber(weather.humidity)}% humidity
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#666' }}>
            Last updated: {formatDateTime(lastUpdate)}
          </div>
        </div>

        <div className="map-container">
          <button className="refresh-button" onClick={loadData}>
            Refresh Data
          </button>
          
          <div className="legend">
            <h4>Temperature Legend</h4>
            <div className="legend-item">
              <div className="legend-color" style={{backgroundColor: '#0066cc'}}></div>
              <span>&lt; 0°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{backgroundColor: '#0099ff'}}></div>
              <span>0-10°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{backgroundColor: '#00cc00'}}></div>
              <span>10-20°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{backgroundColor: '#ffcc00'}}></div>
              <span>20-30°C</span>
            </div>
            <div className="legend-item">
              <div className="legend-color" style={{backgroundColor: '#ff6600'}}></div>
              <span>&gt; 30°C</span>
            </div>
          </div>
          
          <MapContainer
            center={[46.5, 27.0]}
            zoom={6}
            style={{ height: '100%', width: '100%' }}
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            
            {weatherData.map((weather, index) => (
              <CircleMarker
                key={index}
                center={[weather.latitude, weather.longitude]}
                radius={15}
                fillColor={getTemperatureColor(weather.temperature)}
                color="white"
                weight={2}
                opacity={1}
                fillOpacity={0.8}
              >
                <Popup>
                  <div style={{ minWidth: '200px' }}>
                    <h4 style={{ margin: '0 0 10px 0' }}>
                      {weather.city}, {weather.country}
                    </h4>
                    <table style={{ width: '100%', fontSize: '0.9rem' }}>
                      <tbody>
                        <tr>
                          <td><strong>Temperature:</strong></td>
                          <td>{formatNumber(weather.temperature)}°C</td>
                        </tr>
                        <tr>
                          <td><strong>Feels like:</strong></td>
                          <td>{formatNumber(weather.apparent_temperature)}°C</td>
                        </tr>
                        <tr>
                          <td><strong>Humidity:</strong></td>
                          <td>{formatNumber(weather.humidity)}%</td>
                        </tr>
                        <tr>
                          <td><strong>Wind Speed:</strong></td>
                          <td>{formatNumber(weather.windspeed)} m/s</td>
                        </tr>
                        <tr>
                          <td><strong>Pressure:</strong></td>
                          <td>{formatNumber(weather.pressure_msl)} hPa</td>
                        </tr>
                        <tr>
                          <td><strong>Cloud Cover:</strong></td>
                          <td>{weather.cloud_cover || 'N/A'}%</td>
                        </tr>
                        <tr>
                          <td><strong>UV Index:</strong></td>
                          <td>{formatNumber(weather.uv_index)}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div style={{ marginTop: '10px', fontSize: '0.8rem', color: '#666' }}>
                      Last update: {formatDateTime(weather.measurement_datetime)}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                      Quality: {weather.quality_score ? (weather.quality_score * 100).toFixed(0) + '%' : 'N/A'}
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}

            {/* Show all locations without weather data */}
            {locations
              .filter(loc => !weatherData.find(w => w.city === loc.city))
              .map((location, index) => (
                <Marker
                  key={`loc-${index}`}
                  position={[location.latitude, location.longitude]}
                >
                  <Popup>
                    <div>
                      <h4>{location.city}, {location.country}</h4>
                      <p>{location.location_name}</p>
                      <p>Area: {location.campus_area}</p>
                      <p><em>No recent weather data</em></p>
                    </div>
                  </Popup>
                </Marker>
              ))
            }
          </MapContainer>
        </div>
      </div>
    </div>
  );
}

export default App;
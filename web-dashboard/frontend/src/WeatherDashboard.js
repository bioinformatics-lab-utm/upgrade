import React, { useState, useEffect } from 'react';
import WeatherMap from './components/WeatherMap';
import StatsPanel from './components/StatsPanel';
import StationDetails from './components/StationDetails';
import { weatherAPI } from './services/api';
import './App.css';

function App() {
  const [stations, setStations] = useState([]);
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [selectedStation, setSelectedStation] = useState(null);
  const [stationHistory, setStationHistory] = useState(null);
  const [selectedMetric, setSelectedMetric] = useState('temperature');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Загрузка данных при монтировании
  useEffect(() => {
    loadAllData();
    
    // Автообновление каждые 5 минут
    const interval = setInterval(loadAllData, 5 * 60 * 1000);
    
    return () => clearInterval(interval);
  }, []);

  const loadAllData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [stationsData, statsData, alertsData] = await Promise.all([
        weatherAPI.getStations(),
        weatherAPI.getStats(),
        weatherAPI.getAlerts(),
      ]);

      setStations(stationsData.stations || []);
      setStats(statsData);
      setAlerts(alertsData.alerts || []);
    } catch (err) {
      console.error('Error loading data:', err);
      setError('Failed to load weather data. Please check if the API is running.');
    } finally {
      setLoading(false);
    }
  };

  const handleStationClick = async (station) => {
    setSelectedStation(station);
    
    try {
      const history = await weatherAPI.getStationHistory(station.id, 24);
      setStationHistory(history);
    } catch (err) {
      console.error('Error loading station history:', err);
    }
  };

  const handleCloseDetails = () => {
    setSelectedStation(null);
    setStationHistory(null);
  };

  if (loading && stations.length === 0) {
    return (
      <div className="app loading-screen">
        <div className="loader"></div>
        <p>Loading weather data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app error-screen">
        <div className="error-message">
          <h2>⚠️ Error</h2>
          <p>{error}</p>
          <button onClick={loadAllData}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🌤️ Weather Geo Dashboard</h1>
        <div className="header-controls">
          <div className="metric-selector">
            <label>Color by:</label>
            <select 
              value={selectedMetric} 
              onChange={(e) => setSelectedMetric(e.target.value)}
            >
              <option value="temperature">Temperature</option>
              <option value="humidity">Humidity</option>
              <option value="wind_speed">Wind Speed</option>
              <option value="precipitation">Precipitation</option>
            </select>
          </div>
          <button className="refresh-btn" onClick={loadAllData}>
            🔄 Refresh
          </button>
        </div>
      </header>

      <div className="app-content">
        <aside className="sidebar">
          <StatsPanel stats={stats} alerts={alerts} />
        </aside>

        <main className="main-content">
          <div className="map-container">
            <WeatherMap 
              stations={stations}
              onStationClick={handleStationClick}
              selectedMetric={selectedMetric}
            />
          </div>
        </main>
      </div>

      {selectedStation && (
        <StationDetails
          station={selectedStation}
          history={stationHistory}
          onClose={handleCloseDetails}
        />
      )}

      <footer className="app-footer">
        <p>Weather stations: {stations.length} | Last update: {new Date().toLocaleTimeString()}</p>
      </footer>
    </div>
  );
}

export default App;
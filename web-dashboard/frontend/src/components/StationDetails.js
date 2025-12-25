import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './StationDetails.css';

const StationDetails = ({ station, history, onClose }) => {
  if (!station) return null;

  // Подготовка данных для графика
  const chartData = history?.history?.map(reading => ({
    time: new Date(reading.timestamp).toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit' 
    }),
    temperature: reading.temperature,
    humidity: reading.humidity,
    wind_speed: reading.wind_speed,
  })).reverse() || [];

  return (
    <div className="station-details-overlay" onClick={onClose}>
      <div className="station-details" onClick={(e) => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose}>×</button>
        
        <div className="details-header">
          <h2>{station.name}</h2>
          <p className="station-location">
            📍 {station.region}, {station.country}
          </p>
          <p className="station-coords">
            Coordinates: {station.latitude?.toFixed(4)}°N, {station.longitude?.toFixed(4)}°E
            {station.elevation && ` | Elevation: ${station.elevation}m`}
          </p>
        </div>

        <div className="current-conditions">
          <h3>Current Conditions</h3>
          <div className="conditions-grid">
            {station.temperature !== null && (
              <div className="condition-card">
                <div className="condition-icon">🌡️</div>
                <div className="condition-value">{station.temperature.toFixed(1)}°C</div>
                <div className="condition-label">Temperature</div>
              </div>
            )}
            {station.humidity !== null && (
              <div className="condition-card">
                <div className="condition-icon">💧</div>
                <div className="condition-value">{station.humidity.toFixed(0)}%</div>
                <div className="condition-label">Humidity</div>
              </div>
            )}
            {station.wind_speed !== null && (
              <div className="condition-card">
                <div className="condition-icon">💨</div>
                <div className="condition-value">{station.wind_speed.toFixed(1)} m/s</div>
                <div className="condition-label">Wind Speed</div>
              </div>
            )}
            {station.precipitation !== null && (
              <div className="condition-card">
                <div className="condition-icon">🌧️</div>
                <div className="condition-value">{station.precipitation.toFixed(1)} mm</div>
                <div className="condition-label">Precipitation</div>
              </div>
            )}
          </div>
        </div>

        {chartData.length > 0 && (
          <div className="history-charts">
            <h3>24-Hour History</h3>
            
            <div className="chart-container">
              <h4>Temperature (°C)</h4>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 12 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis />
                  <Tooltip />
                  <Line 
                    type="monotone" 
                    dataKey="temperature" 
                    stroke="#ff6b6b" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-container">
              <h4>Humidity (%)</h4>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 12 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis />
                  <Tooltip />
                  <Line 
                    type="monotone" 
                    dataKey="humidity" 
                    stroke="#4dabf7" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-container">
              <h4>Wind Speed (m/s)</h4>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 12 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis />
                  <Tooltip />
                  <Line 
                    type="monotone" 
                    dataKey="wind_speed" 
                    stroke="#51cf66" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {station.last_update && (
          <div className="last-update-info">
            Last updated: {new Date(station.last_update).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
};

export default StationDetails;
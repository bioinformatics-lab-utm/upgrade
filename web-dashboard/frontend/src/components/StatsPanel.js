import React from 'react';
import './StatsPanel.css';

const StatsPanel = ({ stats, alerts }) => {
  if (!stats) {
    return (
      <div className="stats-panel">
        <div className="loading">Loading statistics...</div>
      </div>
    );
  }

  const { stations_count, readings_24h, averages, extremes } = stats;

  return (
    <div className="stats-panel">
      <h2>📊 Statistics</h2>
      
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">📍</div>
          <div className="stat-content">
            <div className="stat-value">{stations_count}</div>
            <div className="stat-label">Weather Stations</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">📈</div>
          <div className="stat-content">
            <div className="stat-value">{readings_24h?.toLocaleString()}</div>
            <div className="stat-label">Readings (24h)</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">🌡️</div>
          <div className="stat-content">
            <div className="stat-value">
              {averages?.temperature !== null 
                ? `${averages.temperature.toFixed(1)}°C` 
                : 'N/A'}
            </div>
            <div className="stat-label">Avg Temperature</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💧</div>
          <div className="stat-content">
            <div className="stat-value">
              {averages?.humidity !== null 
                ? `${averages.humidity.toFixed(0)}%` 
                : 'N/A'}
            </div>
            <div className="stat-label">Avg Humidity</div>
          </div>
        </div>
      </div>

      <div className="extremes-section">
        <h3>🔥 Extremes (24h)</h3>
        <div className="extremes-grid">
          <div className="extreme-item">
            <span className="extreme-label">Max Temp:</span>
            <span className="extreme-value hot">
              {extremes?.max_temperature !== null 
                ? `${extremes.max_temperature.toFixed(1)}°C` 
                : 'N/A'}
            </span>
          </div>
          <div className="extreme-item">
            <span className="extreme-label">Min Temp:</span>
            <span className="extreme-value cold">
              {extremes?.min_temperature !== null 
                ? `${extremes.min_temperature.toFixed(1)}°C` 
                : 'N/A'}
            </span>
          </div>
          <div className="extreme-item">
            <span className="extreme-label">Max Wind:</span>
            <span className="extreme-value wind">
              {extremes?.max_wind_speed !== null 
                ? `${extremes.max_wind_speed.toFixed(1)} m/s` 
                : 'N/A'}
            </span>
          </div>
        </div>
      </div>

      {alerts && alerts.length > 0 && (
        <div className="alerts-section">
          <h3>⚠️ Active Alerts</h3>
          <div className="alerts-list">
            {alerts.slice(0, 5).map((alert, index) => (
              <div key={index} className={`alert-item ${alert.alert_type}`}>
                <div className="alert-station">{alert.station_name}</div>
                <div className="alert-info">
                  {alert.alert_type.replace('_', ' ').toUpperCase()}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default StatsPanel;
import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, CircleMarker } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './Map.css';

// Иконка для маркера
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const WeatherMap = ({ stations, onStationClick, selectedMetric }) => {
  const [center, setCenter] = useState([47.0, 28.8]); // Chisinau coordinates
  const [zoom, setZoom] = useState(7);

  useEffect(() => {
    // Автоматическое центрирование на станциях
    if (stations && stations.length > 0) {
      const validStations = stations.filter(s => s.latitude && s.longitude);
      if (validStations.length > 0) {
        const avgLat = validStations.reduce((sum, s) => sum + s.latitude, 0) / validStations.length;
        const avgLon = validStations.reduce((sum, s) => sum + s.longitude, 0) / validStations.length;
        setCenter([avgLat, avgLon]);
      }
    }
  }, [stations]);

  const getMarkerColor = (station) => {
    if (!selectedMetric || !station[selectedMetric]) return '#3388ff';

    const value = station[selectedMetric];
    
    if (selectedMetric === 'temperature') {
      if (value < 0) return '#0066cc';
      if (value < 10) return '#00aaff';
      if (value < 20) return '#00ff00';
      if (value < 30) return '#ffaa00';
      return '#ff0000';
    }
    
    if (selectedMetric === 'wind_speed') {
      if (value < 5) return '#00ff00';
      if (value < 15) return '#ffaa00';
      return '#ff0000';
    }
    
    if (selectedMetric === 'humidity') {
      if (value < 30) return '#ffaa00';
      if (value < 70) return '#00ff00';
      return '#0066cc';
    }
    
    return '#3388ff';
  };

  const getMetricValue = (station) => {
    if (!selectedMetric || !station[selectedMetric]) return 'N/A';
    
    const value = station[selectedMetric];
    
    switch (selectedMetric) {
      case 'temperature':
        return `${value.toFixed(1)}°C`;
      case 'wind_speed':
        return `${value.toFixed(1)} m/s`;
      case 'humidity':
        return `${value.toFixed(0)}%`;
      case 'precipitation':
        return `${value.toFixed(1)} mm`;
      default:
        return value.toFixed(1);
    }
  };

  return (
    <MapContainer 
      center={center} 
      zoom={zoom} 
      style={{ height: '100%', width: '100%' }}
      className="weather-map"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      
      {stations && stations.map((station) => {
        if (!station.latitude || !station.longitude) return null;
        
        const color = getMarkerColor(station);
        
        return (
          <CircleMarker
            key={station.id}
            center={[station.latitude, station.longitude]}
            radius={8}
            fillColor={color}
            color="#fff"
            weight={2}
            opacity={1}
            fillOpacity={0.8}
            eventHandlers={{
              click: () => onStationClick && onStationClick(station),
            }}
          >
            <Popup>
              <div className="station-popup">
                <h3>{station.name}</h3>
                <p className="region">{station.region}, {station.country}</p>
                <div className="metrics">
                  {station.temperature !== null && (
                    <div className="metric">
                      <span className="label">🌡️ Temperature:</span>
                      <span className="value">{station.temperature.toFixed(1)}°C</span>
                    </div>
                  )}
                  {station.humidity !== null && (
                    <div className="metric">
                      <span className="label">💧 Humidity:</span>
                      <span className="value">{station.humidity.toFixed(0)}%</span>
                    </div>
                  )}
                  {station.wind_speed !== null && (
                    <div className="metric">
                      <span className="label">💨 Wind:</span>
                      <span className="value">{station.wind_speed.toFixed(1)} m/s</span>
                    </div>
                  )}
                  {station.precipitation !== null && (
                    <div className="metric">
                      <span className="label">🌧️ Precipitation:</span>
                      <span className="value">{station.precipitation.toFixed(1)} mm</span>
                    </div>
                  )}
                </div>
                {station.last_update && (
                  <p className="last-update">
                    Updated: {new Date(station.last_update).toLocaleString()}
                  </p>
                )}
                <button 
                  className="details-btn"
                  onClick={() => onStationClick && onStationClick(station)}
                >
                  View Details
                </button>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
};

export default WeatherMap;
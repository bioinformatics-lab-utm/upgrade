import React from 'react';
import { CircleMarker, Popup } from 'react-leaflet';

const WeatherMarker = ({ weather, getTemperatureColor, formatNumber, formatDateTime }) => {
  return (
    <CircleMarker
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
  );
};

export default WeatherMarker;
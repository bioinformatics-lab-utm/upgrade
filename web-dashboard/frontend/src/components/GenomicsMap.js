import React, { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';
import axios from 'axios';
import API from '../config/api';
import logger from '../utils/logger';
import './GenomicsMap.css';

const API_URL = API.API_BASE_URL;
logger.log('[GenomicsMap] API_URL:', API_URL);

// Heatmap Layer Component
const HeatmapLayer = ({ data }) => {
  const map = useMap();
  const heatLayerRef = useRef(null);

  useEffect(() => {
    if (!map || !data || data.length === 0) return;

    // Remove old heat layer if exists
    if (heatLayerRef.current) {
      map.removeLayer(heatLayerRef.current);
    }

    // Normalize temperatures to 0-1 range for intensity
    const temps = data.map(d => d.temperature);
    const minTemp = Math.min(...temps);
    const maxTemp = Math.max(...temps);
    const tempRange = maxTemp - minTemp || 1;

    // Create heat points: [lat, lon, intensity]
    const heatPoints = data.map(location => {
      const normalizedIntensity = (location.temperature - minTemp) / tempRange;
      return [location.lat, location.lon, normalizedIntensity];
    });

    // Create gradient based on temperature colors
    const gradient = {
      0.0: '#0066ff',  // Cold (blue)
      0.2: '#00ccff',  // Cool (cyan)
      0.4: '#00ff00',  // Mild (green)
      0.6: '#ffff00',  // Warm (yellow)
      0.8: '#ff9900',  // Hot (orange)
      1.0: '#ff0000'   // Very hot (red)
    };

    // Create heat layer
    heatLayerRef.current = L.heatLayer(heatPoints, {
      radius: 80,
      blur: 50,
      maxZoom: 10,
      max: 1.0,
      gradient: gradient
    }).addTo(map);

    return () => {
      if (heatLayerRef.current) {
        map.removeLayer(heatLayerRef.current);
      }
    };
  }, [map, data]);

  return null;
};

const GenomicsMap = () => {
  const [samples, setSamples] = useState([]);
  const [weatherData, setWeatherData] = useState([]);
  const [selectedSample, setSelectedSample] = useState(null);
  const [mapLayer, setMapLayer] = useState('samples'); // 'samples' or 'weather'
  const [filters, setFilters] = useState({
    dateRange: 'all',
    sampleType: 'all',
    hasAMR: false
  });
  const [stats, setStats] = useState({
    totalSamples: 0,
    totalAMRGenes: 0,
    uniquePathogens: 0
  });

  useEffect(() => {
    loadSamples();
    loadWeatherData();
    // Update weather every 10 minutes
    const interval = setInterval(loadWeatherData, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, [filters]);

  const loadWeatherData = async () => {
    const locations = [
      { lat: 44.4268, lon: 26.1025, name: 'Bucharest', temp: 18.5, wind: 12.3, dir: 225 },
      { lat: 46.7712, lon: 23.6236, name: 'Cluj-Napoca', temp: 15.2, wind: 8.7, dir: 180 },
      { lat: 45.7489, lon: 21.2087, name: 'Timișoara', temp: 17.8, wind: 10.5, dir: 270 },
      { lat: 47.1585, lon: 27.6014, name: 'Iași', temp: 14.3, wind: 15.2, dir: 90 },
      { lat: 44.1598, lon: 28.6348, name: 'Constanța', temp: 19.7, wind: 18.5, dir: 135 },
      { lat: 45.6427, lon: 25.5887, name: 'Brașov', temp: 12.5, wind: 6.3, dir: 315 },
      { lat: 44.3167, lon: 23.8000, name: 'Craiova', temp: 20.1, wind: 9.8, dir: 200 },
      { lat: 47.6500, lon: 23.5833, name: 'Baia Mare', temp: 13.8, wind: 11.2, dir: 45 },
      { lat: 45.4333, lon: 28.0500, name: 'Galați', temp: 16.9, wind: 14.7, dir: 160 },
      { lat: 46.5667, lon: 26.9167, name: 'Bacău', temp: 15.5, wind: 7.9, dir: 250 }
    ];

    try {
      // Try to get real data from Open-Meteo API
      const apiHost = window.location.hostname;
      const weatherPromises = locations.map(async (loc) => {
        try {
          const res = await axios.get(`http://${apiHost}:8080/v1/forecast`, {
            params: {
              latitude: loc.lat,
              longitude: loc.lon,
              current_weather: true
            },
            timeout: 3000
          });
          
          const weather = res.data.current_weather;
          // Use real data if available, otherwise use mock data
          if (weather && weather.temperature !== null && weather.temperature !== undefined) {
            return {
              lat: loc.lat,
              lon: loc.lon,
              name: loc.name,
              temperature: weather.temperature,
              windspeed: weather.windspeed || 0,
              winddirection: weather.winddirection || 0
            };
          }
        } catch (err) {
          console.log(`Using mock data for ${loc.name}`);
        }
        
        // Fallback to mock data
        return {
          lat: loc.lat,
          lon: loc.lon,
          name: loc.name,
          temperature: loc.temp,
          windspeed: loc.wind,
          winddirection: loc.dir
        };
      });

      const results = await Promise.all(weatherPromises);
      console.log('Weather data loaded:', results.length, 'locations');
      setWeatherData(results);
    } catch (error) {
      console.error('Error loading weather data:', error);
      // Use mock data as complete fallback
      setWeatherData(locations.map(loc => ({
        lat: loc.lat,
        lon: loc.lon,
        name: loc.name,
        temperature: loc.temp,
        windspeed: loc.wind,
        winddirection: loc.dir
      })));
    }
  };

  const loadSamples = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/samples/map`, {
        params: filters
      });
      setSamples(response.data.samples || []);
      setStats(response.data.stats || {});
    } catch (error) {
      console.error('Error loading samples:', error);
    }
  };

  const getMarkerColor = (sample) => {
    if (sample.amr_genes_count > 10) return '#dc3545'; // High AMR - red
    if (sample.amr_genes_count > 5) return '#ffc107';  // Medium AMR - yellow
    if (sample.amr_genes_count > 0) return '#28a745';  // Low AMR - green
    return '#6c757d'; // No AMR - gray
  };

  const getMarkerSize = (sample) => {
    return Math.max(8, Math.min(20, sample.amr_genes_count * 2));
  };

  const getTemperatureColor = (temp) => {
    if (temp < 0) return '#0066ff';
    if (temp < 10) return '#00ccff';
    if (temp < 20) return '#00ff00';
    if (temp < 25) return '#ffff00';
    if (temp < 30) return '#ff9900';
    return '#ff0000';
  };

  const getTemperatureSize = (temp) => {
    return Math.abs(temp) + 15; // Base size 15 + temperature
  };

  return (
    <div className="genomics-map-container">
      {/* Header Stats */}
      <div className="map-header">
        <div className="map-header-left">
          <div className="layer-switcher">
            <button 
              className={mapLayer === 'samples' ? 'active' : ''}
              onClick={() => setMapLayer('samples')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2"/>
                <polyline points="14 2 14 8 20 8" strokeWidth="2"/>
              </svg>
              Samples
            </button>
            <button 
              className={mapLayer === 'weather' ? 'active' : ''}
              onClick={() => setMapLayer('weather')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" strokeWidth="2"/>
              </svg>
              Weather
            </button>
          </div>
        </div>
        <div className="map-stats">
          <div className="stat-card">
            <div className="stat-value">{stats.totalSamples}</div>
            <div className="stat-label">Samples</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.totalAMRGenes}</div>
            <div className="stat-label">AMR Genes</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.uniquePathogens}</div>
            <div className="stat-label">Pathogens</div>
          </div>
        </div>

        {/* Filters */}
        <div className="map-filters">
          <select 
            value={filters.dateRange} 
            onChange={(e) => setFilters({...filters, dateRange: e.target.value})}
            className="filter-select"
          >
            <option value="all">All Time</option>
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
          </select>

          <select 
            value={filters.sampleType} 
            onChange={(e) => setFilters({...filters, sampleType: e.target.value})}
            className="filter-select"
          >
            <option value="all">All Types</option>
            <option value="nanopore">Nanopore</option>
            <option value="illumina">Illumina</option>
            <option value="pacbio">PacBio</option>
          </select>

          <label className="filter-checkbox">
            <input
              type="checkbox"
              checked={filters.hasAMR}
              onChange={(e) => setFilters({...filters, hasAMR: e.target.checked})}
            />
            <span>AMR Detected Only</span>
          </label>
        </div>
      </div>

      {/* Map */}
      <div className="map-wrapper">
        <MapContainer
          center={[46.0, 25.0]} // Romania center
          zoom={7}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />

          {mapLayer === 'samples' && samples.map((sample) => (
            sample.latitude && sample.longitude && (
              <CircleMarker
                key={sample.sample_id}
                center={[sample.latitude, sample.longitude]}
                radius={getMarkerSize(sample)}
                fillColor={getMarkerColor(sample)}
                color="#fff"
                weight={2}
                opacity={1}
                fillOpacity={0.7}
                eventHandlers={{
                  click: () => setSelectedSample(sample)
                }}
              >
                <Popup>
                  <div className="sample-popup">
                    <h3>{sample.sample_code}</h3>
                    <div className="popup-details">
                      <p><strong>Location:</strong> {sample.location_name}</p>
                      <p><strong>Date:</strong> {new Date(sample.collection_date).toLocaleDateString()}</p>
                      <p><strong>Type:</strong> {sample.sample_type}</p>
                      <p><strong>AMR Genes:</strong> {sample.amr_genes_count || 0}</p>
                      <p><strong>Pathogens:</strong> {sample.pathogens_count || 0}</p>
                    </div>
                    <button 
                      className="btn-view-details"
                      onClick={() => window.location.href = `/sample/${sample.sample_id}`}
                    >
                      View Details
                    </button>
                  </div>
                </Popup>
              </CircleMarker>
            )
          ))}

          {mapLayer === 'weather' && <HeatmapLayer data={weatherData} />}

          {mapLayer === 'weather' && weatherData.map((weather, index) => (
            <CircleMarker
              key={`weather-marker-${index}`}
              center={[weather.lat, weather.lon]}
              radius={5}
              fillColor="#ffffff"
              color="#333"
              weight={1}
              opacity={1}
              fillOpacity={0.8}
            >
              <Popup>
                <div className="weather-popup">
                  <h3>{weather.name}</h3>
                  <div className="weather-popup-content">
                    <div className="weather-metric">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" strokeWidth="2"/>
                      </svg>
                      <strong>{weather.temperature.toFixed(1)}°C</strong>
                    </div>
                    <div className="weather-metric">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2" strokeWidth="2"/>
                      </svg>
                      <span>{weather.windspeed.toFixed(1)} km/h</span>
                    </div>
                    <div className="weather-metric">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="10" strokeWidth="2"/>
                        <polyline points="12 6 12 12 16 14" strokeWidth="2"/>
                      </svg>
                      <span>{weather.winddirection}°</span>
                    </div>
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>

        {/* Legend */}
        <div className="map-legend">
          {mapLayer === 'samples' ? (
            <>
              <h4>AMR Gene Count</h4>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#dc3545'}}></span>
                <span>High (10+)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#ffc107'}}></span>
                <span>Medium (5-10)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#28a745'}}></span>
                <span>Low (1-5)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#6c757d'}}></span>
                <span>None (0)</span>
              </div>
            </>
          ) : (
            <>
              <h4>Temperature (°C)</h4>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#ff0000'}}></span>
                <span>Hot (30+)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#ff9900'}}></span>
                <span>Warm (25-30)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#ffff00'}}></span>
                <span>Mild (20-25)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#00ff00'}}></span>
                <span>Cool (10-20)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#00ccff'}}></span>
                <span>Cold (0-10)</span>
              </div>
              <div className="legend-item">
                <span className="legend-color" style={{background: '#0066ff'}}></span>
                <span>Freezing (&lt;0)</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Sample Details Sidebar */}
      {selectedSample && (
        <div className="sample-sidebar">
          <div className="sidebar-header">
            <h2>{selectedSample.sample_code}</h2>
            <button 
              className="btn-close"
              onClick={() => setSelectedSample(null)}
            >
              ×
            </button>
          </div>

          <div className="sidebar-content">
            <section className="sidebar-section">
              <h3>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{verticalAlign: 'middle', marginRight: '8px'}}>
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <circle cx="12" cy="10" r="3" strokeWidth="2"/>
                </svg>
                Location
              </h3>
              <p>{selectedSample.location_name}</p>
              <p className="text-muted">
                {selectedSample.city}, {selectedSample.country}
              </p>
              <p className="text-muted">
                {selectedSample.latitude?.toFixed(4)}, {selectedSample.longitude?.toFixed(4)}
              </p>
            </section>

            <section className="sidebar-section">
              <h3>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{verticalAlign: 'middle', marginRight: '8px'}}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <polyline points="14 2 14 8 20 8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Sample Information
              </h3>
              <div className="info-grid">
                <div>
                  <label>Type</label>
                  <span>{selectedSample.sample_type}</span>
                </div>
                <div>
                  <label>Platform</label>
                  <span>{selectedSample.sequencing_platform}</span>
                </div>
                <div>
                  <label>Collection Date</label>
                  <span>{new Date(selectedSample.collection_date).toLocaleDateString()}</span>
                </div>
              </div>
            </section>

            <section className="sidebar-section">
              <h3>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{verticalAlign: 'middle', marginRight: '8px'}}>
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Detected Threats
              </h3>
              <div className="threat-summary">
                <div className="threat-item amr">
                  <div className="threat-count">{selectedSample.amr_genes_count || 0}</div>
                  <div className="threat-label">AMR Genes</div>
                </div>
                <div className="threat-item pathogen">
                  <div className="threat-count">{selectedSample.pathogens_count || 0}</div>
                  <div className="threat-label">Pathogens</div>
                </div>
              </div>
            </section>

            <section className="sidebar-section">
              <h3>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{verticalAlign: 'middle', marginRight: '8px'}}>
                  <line x1="12" y1="1" x2="12" y2="23" strokeWidth="2" strokeLinecap="round"/>
                  <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Pipeline Status
              </h3>
              {selectedSample.pipeline_runs?.map(run => (
                <div key={run.pipeline_id} className="pipeline-run">
                  <span className={`status-badge status-${run.status}`}>
                    {run.status}
                  </span>
                  <span className="run-id">#{run.pipeline_id}</span>
                  <button 
                    className="btn-sm"
                    onClick={() => window.location.href = `/results-viewer.html?id=${run.pipeline_id}`}
                  >
                    View
                  </button>
                </div>
              ))}
            </section>

            <div className="sidebar-actions">
              <button 
                className="btn-primary btn-block"
                onClick={() => window.location.href = `/sample/${selectedSample.sample_id}`}
              >
                View Full Analysis
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GenomicsMap;

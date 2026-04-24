import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import logger from '../../utils/logger';

// Custom icons for different risk levels
const createCustomIcon = (riskLevel, sampleType) => {
  const colors = {
    high: '#dc2626',    // red
    medium: '#f59e0b',  // orange
    low: '#eab308',     // yellow
    none: '#16a34a'     // green
  };

  const icons = {
    'user_upload': '🧬',
    'sra_auto': '📊',
  };

  return L.divIcon({
    html: `
      <div style="
        background-color: ${colors[riskLevel] || colors.none};
        width: 20px;
        height: 20px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        border: 2px solid white;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
      ">
        ${icons[sampleType] || '📍'}
      </div>
    `,
    className: 'custom-marker',
    iconSize: [20, 20],
    iconAnchor: [10, 10]
  });
};

const InteractiveMap = () => {
  const [samples, setSamples] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedSample, setSelectedSample] = useState(null);
  const [filters, setFilters] = useState({
    riskLevel: 'all',
    sampleType: 'all',
  });

  // Fetch initial data
  useEffect(() => {
    Promise.all([
      fetchSamples(),
      fetchStats()
    ]).finally(() => setLoading(false));
  }, []);

  const fetchSamples = async () => {
    try {
      const response = await fetch('/api/samples/map');
      const data = await response.json();
      setSamples(data.samples);
    } catch (error) {
      console.error('Error fetching samples:', error);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/samples/stats');
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  };

  // Filter samples based on selected filters
  const filteredSamples = samples.filter(sample => {
    if (filters.riskLevel !== 'all' && sample.risk_level !== filters.riskLevel) {
      return false;
    }
    if (filters.sampleType !== 'all' && sample.source_type !== filters.sampleType) {
      return false;
    }
    return true;
  });

  const SamplePopup = ({ sample }) => (
    <div className="sample-popup">
      <h3>{sample.name}</h3>
      <p><strong>Location:</strong> {sample.location_name}</p>
      <p><strong>Type:</strong> {sample.sample_type}</p>
      <p><strong>Status:</strong> 
        <span className={`status status-${sample.status}`}>
          {sample.status.toUpperCase()}
        </span>
      </p>
      <p><strong>Risk Level:</strong> 
        <span className={`risk risk-${sample.risk_level}`}>
          {sample.risk_level.toUpperCase()}
        </span>
      </p>
      <p><strong>Pathogens:</strong> {sample.pathogen_count}</p>
      <p><strong>ARGs:</strong> {sample.arg_count}</p>
      <p><strong>Collection Date:</strong> {new Date(sample.collection_date).toLocaleDateString()}</p>
      
      {sample.status === 'processing' && (
        <div className="processing-indicator">
          <div className="spinner"></div>
          Processing...
        </div>
      )}
    </div>
  );

  if (loading) {
    return (
      <div className="loading-container">
        <div className="spinner-large"></div>
        <p>Loading UPGRADE Dashboard...</p>
      </div>
    );
  }

  return (
    <div className="map-container">
      {/* Stats Panel */}
      <div className="stats-panel">
        <div className="stat-item">
          <span className="stat-value">{stats.total_samples || 0}</span>
          <span className="stat-label">Total Samples</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{stats.processing || 0}</span>
          <span className="stat-label">Processing</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{stats.completed || 0}</span>
          <span className="stat-label">Completed</span>
        </div>
        <div className="stat-item">
          <span className="stat-value">{stats.failed || 0}</span>
          <span className="stat-label">Failed</span>
        </div>
      </div>

      {/* Filters Panel */}
      <div className="filters-panel">
        <div className="filter-group">
          <label>Risk Level:</label>
          <select 
            value={filters.riskLevel} 
            onChange={(e) => setFilters({...filters, riskLevel: e.target.value})}
          >
            <option value="all">All</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
            <option value="none">No Risk</option>
          </select>
        </div>
        
        <div className="filter-group">
          <label>Sample Type:</label>
          <select 
            value={filters.sampleType} 
            onChange={(e) => setFilters({...filters, sampleType: e.target.value})}
          >
            <option value="all">All</option>
            <option value="user_upload">User Uploads</option>
            <option value="sra_auto">SRA Automatic</option>
          </select>
        </div>

        <button onClick={() => {fetchSamples(); fetchStats();}}>
          Refresh Data
        </button>
      </div>

      {/* Interactive Map */}
      <MapContainer
        center={[46.5, 27.0]} // Center between Romania and Moldova
        zoom={6}
        style={{ height: '70vh', width: '100%' }}
        className="leaflet-container"
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        {/* Sample Markers */}
        {filteredSamples.map(sample => (
          <Marker
            key={sample.id}
            position={[sample.latitude, sample.longitude]}
            icon={createCustomIcon(sample.risk_level, sample.source_type)}
            eventHandlers={{
              click: () => setSelectedSample(sample)
            }}
          >
            <Popup>
              <SamplePopup sample={sample} />
            </Popup>
          </Marker>
        ))}

      </MapContainer>

      {/* Sample Details Panel */}
      {selectedSample && (
        <div className="sample-details-panel">
          <button 
            className="close-btn"
            onClick={() => setSelectedSample(null)}
          >
            ×
          </button>
          <SamplePopup sample={selectedSample} />
          
          {selectedSample.status === 'completed' && (
            <div className="analysis-results">
              <h4>Analysis Results</h4>
              <div className="results-grid">
                <div className="result-item">
                  <span className="result-label">Pathogens Detected:</span>
                  <span className="result-value">{selectedSample.pathogen_count}</span>
                </div>
                <div className="result-item">
                  <span className="result-label">ARGs Found:</span>
                  <span className="result-value">{selectedSample.arg_count}</span>
                </div>
                <div className="result-item">
                  <span className="result-label">Risk Assessment:</span>
                  <span className={`result-value risk-${selectedSample.risk_level}`}>
                    {selectedSample.risk_level.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default InteractiveMap;
import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Popup, CircleMarker } from 'react-leaflet';
import api from '../services/api';
import logger from '../utils/logger';
import './GenomicsMap.css';

const API_URL = '';
logger.log('[GenomicsMap] API_URL:', API_URL);

const GenomicsMap = () => {
  const [samples, setSamples] = useState([]);
  const [selectedSample, setSelectedSample] = useState(null);
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
  }, [filters]);

  const loadSamples = async () => {
    try {
      const response = await api.get(`${API_URL}/api/samples/map`, {
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

  return (
    <div className="genomics-map-container">
      {/* Header Stats */}
      <div className="map-header">
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

          {samples.map((sample) => (
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

        </MapContainer>

        {/* Legend */}
        <div className="map-legend">
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

import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import PipelineDashboard from './components/PipelineDashboard';
import GenomicsMap from './components/GenomicsMap';
import ResultsViewer from './components/ResultsViewer';
import 'leaflet/dist/leaflet.css';
import './App.css';

function App() {
  const location = useLocation();

  return (
    <div className="app">
      <nav className="app-nav">
        <div className="app-brand">
          <div className="brand-logo">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M16 4L8 8V16C8 21.5 11.5 26.5 16 28C20.5 26.5 24 21.5 24 16V8L16 4Z" fill="url(#gradient)" />
              <circle cx="16" cy="14" r="3" fill="white" />
              <defs>
                <linearGradient id="gradient" x1="8" y1="4" x2="24" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#667eea" />
                  <stop offset="1" stopColor="#764ba2" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div>
            <h1>UPGRADE</h1>
            <span className="brand-subtitle">Urban Pathogen Genomic Surveillance</span>
          </div>
        </div>
        <div className="nav-links">
          <Link
            to="/"
            className={location.pathname === '/' ? 'active' : ''}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="12" cy="10" r="3" strokeWidth="2"/>
            </svg>
            Map
          </Link>
          <Link
            to="/pipeline"
            className={location.pathname === '/pipeline' ? 'active' : ''}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <polyline points="14 2 14 8 20 8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <line x1="12" y1="18" x2="12" y2="12" strokeWidth="2" strokeLinecap="round"/>
              <line x1="9" y1="15" x2="15" y2="15" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Pipelines
          </Link>
          <Link
            to="/results"
            className={location.pathname === '/results' ? 'active' : ''}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M9 11l3 3L22 4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Results
          </Link>
        </div>
      </nav>

      <main className="app-content">
        <Routes>
          <Route path="/" element={<GenomicsMap />} />
          <Route path="/pipeline" element={<PipelineDashboard />} />
          <Route path="/results" element={<ResultsViewer />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;

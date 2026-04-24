import React, { useState, useEffect } from 'react';
import { Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import PipelineDashboard from './components/PipelineDashboard';
import GenomicsMap from './components/GenomicsMap';
import ResultsViewer from './components/ResultsViewer';
import PipelineResultsDashboard from './components/PipelineResultsDashboard';
import PipelineMonitor from './components/PipelineMonitor';
import Login from './components/Login';
import Register from './components/Register';
import ErrorBoundary from './components/ErrorBoundary';
import API from './config/api';
import 'leaflet/dist/leaflet.css';
import './App.css';

// Protected Route Component
function ProtectedRoute({ children }) {
  const token = localStorage.getItem('token');
  
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  
  return children;
}

function App() {
  const location = useLocation();
  const [systemStatus, setSystemStatus] = useState({ health: 'healthy', samples: 0, pipelines: 0 });
  const [isScrolled, setIsScrolled] = useState(false);
  const [user, setUser] = useState(null);

  useEffect(() => {
    // Check if user is logged in
    const storedUser = localStorage.getItem('user');
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }

    // Fetch system status from health endpoint
    fetch(API.endpoints.health)
      .then(res => res.json())
      .then(data => setSystemStatus({
        health: data.status,
        samples: data.samples_count || 0,
        pipelines: data.active_pipelines || 0
      }))
      .catch(() => setSystemStatus({ health: 'error', samples: 0, pipelines: 0 }));

    // Scroll effect
    const handleScroll = () => setIsScrolled(window.scrollY > 10);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
    window.location.href = '/login';
  };

  const handleLogin = (userData, token) => {
    setUser(userData);
    // Token already stored by Login/Register components
  };

  // Hide navigation on auth pages
  const isAuthPage = location.pathname === '/login' || location.pathname === '/register';

  return (
    <div className="app">
      {/* Enhanced Navigation - Hide on auth pages */}
      {!isAuthPage && (
        <nav className={`app-nav ${isScrolled ? 'scrolled' : ''}`}>
        <div className="nav-container">
          <div className="app-brand">
            <div className="brand-logo">
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="dna-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#00d4ff" />
                    <stop offset="50%" stopColor="#0099ff" />
                    <stop offset="100%" stopColor="#0052ff" />
                  </linearGradient>
                  <filter id="glow">
                    <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
                    <feMerge>
                      <feMergeNode in="coloredBlur"/>
                      <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                  </filter>
                </defs>
                {/* DNA Helix Icon */}
                <path d="M8 10 Q 12 6, 16 10 T 24 10 T 32 10" stroke="url(#dna-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
                <path d="M8 20 Q 12 16, 16 20 T 24 20 T 32 20" stroke="url(#dna-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
                <path d="M8 30 Q 12 26, 16 30 T 24 30 T 32 30" stroke="url(#dna-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
                <circle cx="8" cy="10" r="2" fill="#00d4ff" filter="url(#glow)"/>
                <circle cx="16" cy="10" r="2" fill="#0099ff" filter="url(#glow)"/>
                <circle cx="24" cy="10" r="2" fill="#0052ff" filter="url(#glow)"/>
                <circle cx="32" cy="10" r="2" fill="#00d4ff" filter="url(#glow)"/>
                <circle cx="12" cy="20" r="2" fill="#0099ff" filter="url(#glow)"/>
                <circle cx="20" cy="20" r="2" fill="#0052ff" filter="url(#glow)"/>
                <circle cx="28" cy="20" r="2" fill="#00d4ff" filter="url(#glow)"/>
                <circle cx="8" cy="30" r="2" fill="#0099ff" filter="url(#glow)"/>
                <circle cx="16" cy="30" r="2" fill="#0052ff" filter="url(#glow)"/>
                <circle cx="24" cy="30" r="2" fill="#00d4ff" filter="url(#glow)"/>
                <circle cx="32" cy="30" r="2" fill="#0099ff" filter="url(#glow)"/>
              </svg>
            </div>
            <div className="brand-text">
              <h1>UPGRADE</h1>
              <span className="brand-subtitle">
                <span className="subtitle-icon">⚛</span>
                Urban Pathogen Genomic Surveillance Platform
              </span>
            </div>
          </div>

          {/* System Status Indicator */}
          <div className="system-status">
            <div className="status-item">
              <div className={`status-indicator status-${systemStatus.health}`}></div>
              <span className="status-label">System</span>
            </div>
            <div className="status-divider"></div>
            <div className="status-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M9 11l3 3L22 4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="status-value">{systemStatus.samples}</span>
              <span className="status-label">Samples</span>
            </div>
            <div className="status-divider"></div>
            <div className="status-item">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="2"/>
                <line x1="3" y1="9" x2="21" y2="9" strokeWidth="2"/>
                <line x1="9" y1="21" x2="9" y2="9" strokeWidth="2"/>
              </svg>
              <span className="status-value">{systemStatus.pipelines}</span>
              <span className="status-label">Active</span>
            </div>
          </div>

          {/* Navigation Links */}
          <div className="nav-links">
            <Link
              to="/"
              className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
            >
              <div className="nav-link-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <circle cx="12" cy="10" r="3" strokeWidth="2"/>
                </svg>
              </div>
              <div className="nav-link-content">
                <span className="nav-link-title">Surveillance Map</span>
                <span className="nav-link-desc">Geographic distribution</span>
              </div>
            </Link>

            <Link
              to="/pipeline"
              className={`nav-link ${location.pathname === '/pipeline' ? 'active' : ''}`}
            >
              <div className="nav-link-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <rect x="3" y="3" width="7" height="7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <rect x="14" y="3" width="7" height="7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <rect x="14" y="14" width="7" height="7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <rect x="3" y="14" width="7" height="7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div className="nav-link-content">
                <span className="nav-link-title">Analysis Pipeline</span>
                <span className="nav-link-desc">Workflow management</span>
              </div>
            </Link>

            <Link
              to="/results"
              className={`nav-link ${location.pathname === '/results' ? 'active' : ''}`}
            >
              <div className="nav-link-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M3 3v18h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div className="nav-link-content">
                <span className="nav-link-title">Results & Reports</span>
                <span className="nav-link-desc">Data visualization</span>
              </div>
            </Link>
          </div>

          {/* User Actions */}
          <div className="nav-actions">
            {user ? (
              <>
                <button className="action-btn" title="Notifications">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  <span className="notification-badge">0</span>
                </button>
                <div className="user-profile">
                  <div className="user-avatar" title={user.username}>
                    <span>{user.username.substring(0, 2).toUpperCase()}</span>
                  </div>
                </div>
                <button className="action-btn" onClick={handleLogout} title="Logout">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" strokeWidth="2" strokeLinecap="round"/>
                    <polyline points="16 17 21 12 16 7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <line x1="21" y1="12" x2="9" y2="12" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                </button>
              </>
            ) : (
              <Link to="/login" className="btn btn-primary">
                Login
              </Link>
            )}
          </div>
        </div>
      </nav>
      )}

      {/* Main Content Area */}
      <main className="app-content">
        <div className="content-wrapper">
          <Routes>
            <Route path="/login" element={<Login onLogin={handleLogin} />} />
            <Route path="/register" element={<Register onLogin={handleLogin} />} />
            <Route path="/" element={
              <ProtectedRoute>
                <GenomicsMap />
              </ProtectedRoute>
            } />
            <Route path="/pipeline" element={
              <ProtectedRoute>
                <PipelineDashboard />
              </ProtectedRoute>
            } />
            <Route path="/results" element={
              <ProtectedRoute>
                <ResultsViewer />
              </ProtectedRoute>
            } />
            <Route path="/results/:sampleId" element={
              <ProtectedRoute>
                <PipelineResultsDashboard />
              </ProtectedRoute>
            } />
            <Route path="/pipeline/:id/monitor" element={
              <ProtectedRoute>
                <PipelineMonitor />
              </ProtectedRoute>
            } />
          </Routes>
        </div>
      </main>

      {/* Footer - Hide on auth pages */}
      {!isAuthPage && (
        <footer className="app-footer">
          <div className="footer-content">
            <div className="footer-section">
              <span className="footer-text">© 2025-2026 UPGRADE Platform</span>
              <span className="footer-separator">•</span>
              <span className="footer-text">Build v0.9.0</span>
            </div>
            <div className="footer-section">
              <span className="footer-text">Powered by Nextflow & React</span>
            </div>
          </div>
        </footer>
      )}
    </div>
  );
}

// Wrap App with ErrorBoundary
function AppWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}

export default AppWithErrorBoundary;

import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import apiConfig from '../config/api';
import './Auth.css';

function Login() {
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch(apiConfig.endpoints.auth.login, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });

      const data = await response.json();

      if (response.ok && data.success) {
        // Save token to localStorage
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        
        // Redirect to main page
        navigate('/');
      } else {
        setError(data.error || 'Login failed');
      }
    } catch (err) {
      setError('Network error. Please check if backend is running.');
      console.error('Login error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <svg width="48" height="48" viewBox="0 0 40 40" fill="none">
              <defs>
                <linearGradient id="login-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#00d4ff" />
                  <stop offset="50%" stopColor="#0099ff" />
                  <stop offset="100%" stopColor="#0052ff" />
                </linearGradient>
              </defs>
              <path d="M8 10 Q 12 6, 16 10 T 24 10 T 32 10" stroke="url(#login-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <path d="M8 20 Q 12 16, 16 20 T 24 20 T 32 20" stroke="url(#login-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <path d="M8 30 Q 12 26, 16 30 T 24 30 T 32 30" stroke="url(#login-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <circle cx="8" cy="10" r="2" fill="#00d4ff"/>
              <circle cx="16" cy="10" r="2" fill="#0099ff"/>
              <circle cx="24" cy="10" r="2" fill="#0052ff"/>
              <circle cx="32" cy="10" r="2" fill="#00d4ff"/>
            </svg>
          </div>
          <h1>Welcome Back</h1>
          <p>Sign in to UPGRADE platform</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && (
            <div className="alert alert-error">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <circle cx="12" cy="12" r="10" strokeWidth="2"/>
                <line x1="12" y1="8" x2="12" y2="12" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="12" cy="16" r="1" fill="currentColor"/>
              </svg>
              {error}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              type="text"
              id="username"
              name="username"
              value={formData.username}
              onChange={handleChange}
              placeholder="Enter your username"
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              placeholder="Enter your password"
              required
            />
          </div>

          <button 
            type="submit" 
            className="btn btn-primary btn-block"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="loading-spinner"></span>
                Signing in...
              </>
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" strokeWidth="2" strokeLinecap="round"/>
                  <polyline points="10 17 15 12 10 7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <line x1="15" y1="12" x2="3" y2="12" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                Sign In
              </>
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>Don't have an account? <Link to="/register">Sign up</Link></p>
        </div>
      </div>
    </div>
  );
}

export default Login;

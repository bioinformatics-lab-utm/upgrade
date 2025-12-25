import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import apiConfig from '../config/api';
import './Auth.css';

function Register() {
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    full_name: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [passwordStrength, setPasswordStrength] = useState('');
  const navigate = useNavigate();

  const checkPasswordStrength = (password) => {
    if (!password) return '';
    
    let strength = 0;
    if (password.length >= 8) strength++;
    if (/[a-z]/.test(password)) strength++;
    if (/[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[!@#$%^&*(),.?":{}|<>]/.test(password)) strength++;
    
    if (strength < 3) return 'weak';
    if (strength < 5) return 'medium';
    return 'strong';
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value
    });
    
    if (name === 'password') {
      setPasswordStrength(checkPasswordStrength(value));
    }
    
    setError('');
  };

  const validateForm = () => {
    if (formData.username.length < 3) {
      setError('Username must be at least 3 characters');
      return false;
    }
    
    if (!/^[a-zA-Z0-9_]{3,30}$/.test(formData.username)) {
      setError('Username can only contain letters, numbers, and underscore');
      return false;
    }
    
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      setError('Invalid email format');
      return false;
    }
    
    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters');
      return false;
    }
    
    if (!/[A-Z]/.test(formData.password)) {
      setError('Password must contain at least one uppercase letter');
      return false;
    }
    
    if (!/[a-z]/.test(formData.password)) {
      setError('Password must contain at least one lowercase letter');
      return false;
    }
    
    if (!/\d/.test(formData.password)) {
      setError('Password must contain at least one digit');
      return false;
    }
    
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(formData.password)) {
      setError('Password must contain at least one special character');
      return false;
    }
    
    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return false;
    }
    
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    if (!validateForm()) {
      return;
    }
    
    setLoading(true);

    try {
      const response = await fetch(apiConfig.endpoints.auth.register, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: formData.username,
          email: formData.email,
          password: formData.password,
          full_name: formData.full_name
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        // Save token to localStorage
        localStorage.setItem('token', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        
        // Redirect to main page
        navigate('/');
      } else {
        setError(data.error || 'Registration failed');
      }
    } catch (err) {
      setError('Network error. Please check if backend is running.');
      console.error('Registration error:', err);
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
                <linearGradient id="register-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#00d4ff" />
                  <stop offset="50%" stopColor="#0099ff" />
                  <stop offset="100%" stopColor="#0052ff" />
                </linearGradient>
              </defs>
              <path d="M8 10 Q 12 6, 16 10 T 24 10 T 32 10" stroke="url(#register-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <path d="M8 20 Q 12 16, 16 20 T 24 20 T 32 20" stroke="url(#register-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <path d="M8 30 Q 12 26, 16 30 T 24 30 T 32 30" stroke="url(#register-gradient)" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
              <circle cx="8" cy="10" r="2" fill="#00d4ff"/>
              <circle cx="16" cy="10" r="2" fill="#0099ff"/>
              <circle cx="24" cy="10" r="2" fill="#0052ff"/>
              <circle cx="32" cy="10" r="2" fill="#00d4ff"/>
            </svg>
          </div>
          <h1>Create Account</h1>
          <p>Sign up for UPGRADE platform</p>
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
            <label htmlFor="username">Username *</label>
            <input
              type="text"
              id="username"
              name="username"
              value={formData.username}
              onChange={handleChange}
              placeholder="3-30 characters (letters, numbers, underscore)"
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="email">Email *</label>
            <input
              type="email"
              id="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              placeholder="your.email@example.com"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="full_name">Full Name (optional)</label>
            <input
              type="text"
              id="full_name"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              placeholder="John Doe"
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password *</label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              placeholder="At least 8 characters with uppercase, lowercase, digit, special"
              required
            />
            {passwordStrength && (
              <div className={`password-strength strength-${passwordStrength}`}>
                <div className="strength-bar">
                  <div className="strength-fill"></div>
                </div>
                <span className="strength-text">
                  {passwordStrength === 'weak' && '⚠️ Weak'}
                  {passwordStrength === 'medium' && '⚡ Medium'}
                  {passwordStrength === 'strong' && '✓ Strong'}
                </span>
              </div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password *</label>
            <input
              type="password"
              id="confirmPassword"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              placeholder="Re-enter your password"
              required
            />
          </div>

          <div className="password-requirements">
            <p><strong>Password requirements:</strong></p>
            <ul>
              <li className={formData.password.length >= 8 ? 'met' : ''}>
                ✓ At least 8 characters
              </li>
              <li className={/[A-Z]/.test(formData.password) ? 'met' : ''}>
                ✓ One uppercase letter
              </li>
              <li className={/[a-z]/.test(formData.password) ? 'met' : ''}>
                ✓ One lowercase letter
              </li>
              <li className={/\d/.test(formData.password) ? 'met' : ''}>
                ✓ One digit
              </li>
              <li className={/[!@#$%^&*(),.?":{}|<>]/.test(formData.password) ? 'met' : ''}>
                ✓ One special character
              </li>
            </ul>
          </div>

          <button 
            type="submit" 
            className="btn btn-primary btn-block"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="loading-spinner"></span>
                Creating account...
              </>
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" strokeWidth="2" strokeLinecap="round"/>
                  <circle cx="8.5" cy="7" r="4" strokeWidth="2"/>
                  <line x1="20" y1="8" x2="20" y2="14" strokeWidth="2" strokeLinecap="round"/>
                  <line x1="23" y1="11" x2="17" y2="11" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                Create Account
              </>
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>Already have an account? <Link to="/login">Sign in</Link></p>
        </div>
      </div>
    </div>
  );
}

export default Register;

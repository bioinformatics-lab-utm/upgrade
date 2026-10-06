import React, { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import apiConfig from '../config/api';
import './Auth.css';

// Landing page for the confirmation link sent by email: /verify-email?token=...
function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const [state, setState] = useState(token ? 'loading' : 'invalid'); // loading | verified | expired | invalid | error
  const [error, setError] = useState(token ? '' : 'This confirmation link is invalid.');
  // Tokens are single use, so never submit the same one twice (e.g. StrictMode double effects)
  const submitted = useRef(false);

  useEffect(() => {
    if (!token || submitted.current) return;
    submitted.current = true;

    const verify = async () => {
      try {
        const response = await fetch(apiConfig.endpoints.auth.verifyEmail, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token })
        });
        const data = await response.json();

        if (response.ok && data.success) {
          setState('verified');
        } else {
          setState(data.status === 'expired' ? 'expired' : data.status === 'invalid' ? 'invalid' : 'error');
          setError(data.error || 'Could not confirm your email.');
        }
      } catch (err) {
        setState('error');
        setError('Network error. Please check if backend is running.');
        console.error('Email verification error:', err);
      }
    };

    verify();
  }, [token]);

  return (
    <div className="auth-container">
      <div className="auth-card auth-status">
        {state === 'loading' && (
          <>
            <span className="loading-spinner large"></span>
            <h1>Confirming your email...</h1>
          </>
        )}

        {state === 'verified' && (
          <>
            <div className="auth-status-icon success">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <polyline points="20 6 9 17 4 12" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h1>Email confirmed</h1>
            <p>Your account is active. You can now sign in to UPGRADE.</p>
            <div className="auth-status-actions">
              <Link to="/login?verified=1" className="btn btn-primary btn-block">Sign in</Link>
            </div>
          </>
        )}

        {(state === 'expired' || state === 'invalid' || state === 'error') && (
          <>
            <div className="auth-status-icon error">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <line x1="18" y1="6" x2="6" y2="18" strokeWidth="2.5" strokeLinecap="round"/>
                <line x1="6" y1="6" x2="18" y2="18" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </div>
            <h1>{state === 'expired' ? 'Link expired' : 'Could not confirm email'}</h1>
            <p>{error} You can request a new confirmation email when you sign in.</p>
            <div className="auth-status-actions">
              <Link to="/login" className="btn btn-primary btn-block">Go to sign in</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default VerifyEmail;

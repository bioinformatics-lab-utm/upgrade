import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import apiConfig from '../config/api';
import '../App.css';

function VerifyEmail() {
    const [searchParams] = useSearchParams();
    const [status, setStatus] = useState('verifying');
    const [message, setMessage] = useState('');
    const navigate = useNavigate();
    
    useEffect(() => {
        const token = searchParams.get('token');
        
        if (!token) {
            setStatus('error');
            setMessage('No verification token provided');
            return;
        }
        
        // Verify email with token
        fetch(apiConfig.endpoints.auth.verifyEmail, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ token })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                setStatus('success');
                setMessage(data.message);
                // Redirect to dashboard after 3 seconds
                setTimeout(() => navigate('/'), 3000);
            } else {
                setStatus('error');
                setMessage(data.error);
            }
        })
        .catch(err => {
            console.error('Verification error:', err);
            setStatus('error');
            setMessage('Network error. Please try again.');
        });
    }, [searchParams, navigate]);
    
    return (
        <div className="auth-container">
            <div className="auth-card">
                <div className="auth-logo">
                    <span className="logo-icon">⚛</span>
                    <span className="logo-text">UPGRADE</span>
                </div>
                
                {status === 'verifying' && (
                    <div className="verification-status">
                        <div className="spinner"></div>
                        <h2>Verifying Email...</h2>
                        <p>Please wait while we verify your email address.</p>
                    </div>
                )}
                
                {status === 'success' && (
                    <div className="verification-status success">
                        <svg className="status-icon success-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <h2>Email Verified!</h2>
                        <p className="success-message">{message}</p>
                        <p className="redirect-message">Redirecting to dashboard in 3 seconds...</p>
                    </div>
                )}
                
                {status === 'error' && (
                    <div className="verification-status error">
                        <svg className="status-icon error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <h2>Verification Failed</h2>
                        <p className="error-message">{message}</p>
                        <button className="btn btn-primary" onClick={() => navigate('/login')}>
                            Go to Login
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

export default VerifyEmail;

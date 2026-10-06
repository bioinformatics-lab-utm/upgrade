import React, { useState } from 'react';
import apiConfig from '../config/api';
import './Auth.css';

// Asks the backend to send a fresh confirmation email to an unverified account.
function ResendVerificationButton({ identifier }) {
  const [status, setStatus] = useState('idle'); // idle | sending | sent | error
  const [message, setMessage] = useState('');

  const handleResend = async () => {
    setStatus('sending');
    setMessage('');

    try {
      const response = await fetch(apiConfig.endpoints.auth.resendVerification, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier })
      });
      const data = await response.json();

      if (response.ok && data.success) {
        setStatus('sent');
        setMessage('A new confirmation email has been sent. Check your inbox and spam folder.');
      } else {
        setStatus('error');
        setMessage(data.error || 'Could not send the email. Please try again later.');
      }
    } catch (err) {
      setStatus('error');
      setMessage('Network error. Please check if backend is running.');
      console.error('Resend verification error:', err);
    }
  };

  return (
    <div className="resend-verification">
      {message && (
        <div className={`alert ${status === 'sent' ? 'alert-success' : 'alert-error'}`}>
          {message}
        </div>
      )}
      <button
        type="button"
        className="btn btn-secondary btn-block"
        onClick={handleResend}
        disabled={!identifier || status === 'sending' || status === 'sent'}
      >
        {status === 'sending' ? (
          <>
            <span className="loading-spinner"></span>
            Sending...
          </>
        ) : (
          'Resend confirmation email'
        )}
      </button>
    </div>
  );
}

export default ResendVerificationButton;

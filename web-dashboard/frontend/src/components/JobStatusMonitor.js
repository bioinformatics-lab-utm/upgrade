import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './JobStatusMonitor.css';

const API_URL = process.env.REACT_APP_API_URL || '';

const JobStatusMonitor = ({ jobId, pipelineId, onComplete }) => {
  const [jobStatus, setJobStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!jobId) return;

    // Initial fetch
    fetchJobStatus();

    // Poll every 3 seconds
    const interval = setInterval(fetchJobStatus, 3000);

    return () => clearInterval(interval);
  }, [jobId]);

  const fetchJobStatus = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/pipeline/job/${jobId}/status`);
      setJobStatus(response.data);
      setLoading(false);

      // If job completed or failed, notify parent
      if (response.data.status === 'finished' || response.data.status === 'failed') {
        if (onComplete) {
          onComplete(response.data);
        }
      }
    } catch (err) {
      console.error('Error fetching job status:', err);
      setError(err.message);
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to cancel this job?')) {
      return;
    }

    try {
      await axios.post(`${API_URL}/api/pipeline/job/${jobId}/cancel`);
      fetchJobStatus(); // Refresh status
    } catch (err) {
      alert(`Failed to cancel job: ${err.message}`);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'queued':
        return '⏳';
      case 'started':
        return '▶️';
      case 'finished':
        return '✅';
      case 'failed':
        return '❌';
      case 'cancelled':
        return '🚫';
      default:
        return '❓';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'queued':
        return '#FFA500';
      case 'started':
        return '#2196F3';
      case 'finished':
        return '#4CAF50';
      case 'failed':
        return '#F44336';
      case 'cancelled':
        return '#9E9E9E';
      default:
        return '#757575';
    }
  };

  const formatDuration = (startTime, endTime) => {
    if (!startTime) return 'N/A';

    const start = new Date(startTime);
    const end = endTime ? new Date(endTime) : new Date();
    const durationMs = end - start;

    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  if (loading && !jobStatus) {
    return (
      <div className="job-status-monitor loading">
        <div className="spinner"></div>
        <p>Loading job status...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="job-status-monitor error">
        <p>❌ Error: {error}</p>
      </div>
    );
  }

  if (!jobStatus) {
    return null;
  }

  const isRunning = jobStatus.status === 'queued' || jobStatus.status === 'started';
  const isComplete = jobStatus.status === 'finished';
  const isFailed = jobStatus.status === 'failed';

  return (
    <div className="job-status-monitor">
      <div className="job-header">
        <h3>
          {getStatusIcon(jobStatus.status)} Job Status
        </h3>
        <span
          className="status-badge"
          style={{ backgroundColor: getStatusColor(jobStatus.status) }}
        >
          {jobStatus.status.toUpperCase()}
        </span>
      </div>

      <div className="job-details">
        <div className="detail-row">
          <span className="label">Job ID:</span>
          <span className="value">{jobStatus.job_id}</span>
        </div>

        <div className="detail-row">
          <span className="label">Pipeline ID:</span>
          <span className="value">{pipelineId}</span>
        </div>

        {jobStatus.created_at && (
          <div className="detail-row">
            <span className="label">Created:</span>
            <span className="value">{new Date(jobStatus.created_at).toLocaleString()}</span>
          </div>
        )}

        {jobStatus.started_at && (
          <div className="detail-row">
            <span className="label">Started:</span>
            <span className="value">{new Date(jobStatus.started_at).toLocaleString()}</span>
          </div>
        )}

        {jobStatus.ended_at && (
          <div className="detail-row">
            <span className="label">Ended:</span>
            <span className="value">{new Date(jobStatus.ended_at).toLocaleString()}</span>
          </div>
        )}

        {jobStatus.started_at && (
          <div className="detail-row">
            <span className="label">Duration:</span>
            <span className="value">{formatDuration(jobStatus.started_at, jobStatus.ended_at)}</span>
          </div>
        )}

        {isRunning && (
          <div className="progress-indicator">
            <div className="pulse-dot"></div>
            <span>Pipeline is running... (auto-refreshing every 3s)</span>
          </div>
        )}

        {isComplete && jobStatus.result && (
          <div className="job-result success">
            <h4>✅ Pipeline Completed Successfully</h4>
            {jobStatus.result.output_dir && (
              <p>Results: {jobStatus.result.output_dir}</p>
            )}
          </div>
        )}

        {isFailed && (
          <div className="job-result error">
            <h4>❌ Pipeline Failed</h4>
            {jobStatus.exc_info && (
              <pre className="error-details">{jobStatus.exc_info}</pre>
            )}
          </div>
        )}
      </div>

      <div className="job-actions">
        {isRunning && (
          <button
            className="btn btn-danger"
            onClick={handleCancel}
          >
            Cancel Job
          </button>
        )}

        <button
          className="btn btn-secondary"
          onClick={fetchJobStatus}
        >
          🔄 Refresh Status
        </button>
      </div>
    </div>
  );
};

export default JobStatusMonitor;

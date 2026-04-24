import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './PipelineMonitor.css';
import api from '../services/api';

const PipelineMonitor = ({ pipelineId: propPipelineId, onClose: propOnClose }) => {
  const { id } = useParams();
  const navigate = useNavigate();
  const pipelineId = propPipelineId || id;
  const onClose = propOnClose || (() => {
    // Safe fallback: go to pipeline list if there's no history to go back to
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate('/pipeline');
    }
  });
  
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState('');
  const [logType, setLogType] = useState('nextflow');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const logEndRef = useRef(null);

  // Load pipeline status
  const loadStatus = async () => {
    try {
      const response = await api.get(`/api/monitoring/pipeline/${pipelineId}/status`);
      setStatus(response.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load pipeline logs
  const loadLog = async () => {
    try {
      const response = await api.get(
        `/api/monitoring/pipeline/${pipelineId}/log?lines=200&log_type=${logType}`
      );
      setLog(response.data.content || '');
    } catch (err) {
      console.error('Error loading log:', err);
    }
  };

  // Auto-scroll to bottom of log
  const scrollToBottom = () => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    loadStatus();
    loadLog();
    
    if (autoRefresh) {
      const statusInterval = setInterval(loadStatus, 3000); // Every 3 seconds
      const logInterval = setInterval(loadLog, 5000); // Every 5 seconds
      
      return () => {
        clearInterval(statusInterval);
        clearInterval(logInterval);
      };
    }
  }, [pipelineId, autoRefresh, logType]);

  useEffect(() => {
    scrollToBottom();
  }, [log]);

  if (loading) {
    return (
      <div className="pipeline-monitor-overlay">
        <div className="pipeline-monitor">
          <div className="monitor-loading">Loading pipeline status...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pipeline-monitor-overlay">
        <div className="pipeline-monitor">
          <div className="monitor-error">Error: {error}</div>
          <button onClick={onClose} className="btn-close">Close</button>
        </div>
      </div>
    );
  }

  const { summary, progress, processes, tasks } = status || {};

  return (
    <div className="pipeline-monitor-overlay" onClick={onClose}>
      <div className="pipeline-monitor" onClick={(e) => e.stopPropagation()}>
        <div className="monitor-header">
          <h2>Pipeline #{pipelineId} Monitor</h2>
          <div className="monitor-controls">
            <label className="auto-refresh-toggle">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>Auto-refresh</span>
            </label>
            <button onClick={loadStatus} className="btn-refresh">↻ Refresh</button>
            <button onClick={onClose} className="btn-close">✕ Close</button>
          </div>
        </div>

        {/* Progress Summary */}
        {summary && (
          <div className="progress-summary">
            <div className="progress-bar-container">
              <div className="progress-bar" style={{ width: `${progress}%` }}>
                {progress}%
              </div>
            </div>
            <div className="summary-stats">
              <div className="stat completed">
                <span className="stat-label">Completed</span>
                <span className="stat-value">{summary.completed + summary.cached}</span>
              </div>
              <div className="stat running">
                <span className="stat-label">Running</span>
                <span className="stat-value">{summary.running}</span>
              </div>
              <div className="stat pending">
                <span className="stat-label">Pending</span>
                <span className="stat-value">{summary.pending}</span>
              </div>
              <div className="stat failed">
                <span className="stat-label">Failed</span>
                <span className="stat-value">{summary.failed}</span>
              </div>
              <div className="stat total">
                <span className="stat-label">Total</span>
                <span className="stat-value">{summary.total}</span>
              </div>
            </div>
          </div>
        )}

        {/* Process List */}
        {processes && processes.length > 0 && (
          <div className="processes-section">
            <h3>Processes</h3>
            <div className="processes-grid">
              {processes.map((proc) => (
                <div
                  key={proc.name}
                  className={`process-card ${
                    proc.failed > 0 ? 'failed' :
                    proc.running > 0 ? 'running' :
                    proc.completed === proc.count ? 'completed' :
                    'pending'
                  }`}
                >
                  <div className="process-name">{proc.name}</div>
                  <div className="process-stats">
                    <span className="completed-count">{proc.completed}/{proc.count}</span>
                    {proc.failed > 0 && <span className="failed-badge">⚠ {proc.failed} failed</span>}
                    {proc.running > 0 && <span className="running-badge">▶ {proc.running} running</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Log Viewer */}
        <div className="log-section">
          <div className="log-header">
            <h3>Logs</h3>
            <div className="log-controls">
              <select
                value={logType}
                onChange={(e) => setLogType(e.target.value)}
                className="log-type-select"
              >
                <option value="nextflow">Nextflow Log</option>
                <option value="stdout">Standard Output</option>
                <option value="stderr">Standard Error</option>
              </select>
              <button onClick={loadLog} className="btn-refresh-log">↻</button>
            </div>
          </div>
          <div className="log-viewer">
            <pre className="log-content">{log || 'No logs available yet...'}</pre>
            <div ref={logEndRef} />
          </div>
        </div>

        {/* Task Details Table */}
        {tasks && tasks.length > 0 && (
          <div className="tasks-section">
            <h3>Task Details</h3>
            <div className="tasks-table-container">
              <table className="tasks-table">
                <thead>
                  <tr>
                    <th>Task ID</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Exit</th>
                    <th>Duration</th>
                    <th>CPU</th>
                    <th>Memory</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => (
                    <tr key={task.task_id} className={`status-${task.status.toLowerCase()}`}>
                      <td className="task-id">{task.task_id}</td>
                      <td className="task-name">{task.name}</td>
                      <td className="task-status">
                        <span className={`status-badge ${task.status.toLowerCase()}`}>
                          {task.status}
                        </span>
                      </td>
                      <td className="task-exit">{task.exit}</td>
                      <td className="task-duration">{task.duration}</td>
                      <td className="task-cpu">{task['%cpu']}</td>
                      <td className="task-mem">{task.rss}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default PipelineMonitor;

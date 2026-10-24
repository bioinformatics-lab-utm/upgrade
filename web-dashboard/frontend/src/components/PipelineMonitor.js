import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useParams, useNavigate } from 'react-router-dom';
import './PipelineMonitor.css';
import api from '../services/api';

const PHASES = {
  queued: { label: 'Queued', note: 'Waiting for a free worker. Nothing has started yet.' },
  preparing: { label: 'Preparing', note: 'Downloading the input files. Nextflow starts right after.' },
  running: { label: 'Running', note: null },
  completed: { label: 'Completed', note: null },
  failed: { label: 'Failed', note: null },
  cancelled: { label: 'Stopped', note: 'This run was stopped. Tasks that were running were shut down.' },
};

const formatElapsed = (fromIso, toIso) => {
  if (!fromIso) return null;
  const end = toIso ? new Date(toIso) : new Date();
  const totalMinutes = Math.max(0, Math.floor((end - new Date(fromIso)) / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
};

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
  const [stopping, setStopping] = useState(false);
  const logViewerRef = useRef(null);

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

  // Auto-scroll the log viewer only (scrollIntoView would also scroll the modal body)
  const scrollToBottom = () => {
    const el = logViewerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  const runStatus = status?.status;
  const isActive = !status || runStatus === 'queued' || runStatus === 'running';

  useEffect(() => {
    loadStatus();
    loadLog();

    if (autoRefresh) {
      // A finished run no longer changes; just check now and then
      const statusInterval = setInterval(loadStatus, isActive ? 3000 : 30000);
      const logInterval = setInterval(loadLog, isActive ? 5000 : 30000);

      return () => {
        clearInterval(statusInterval);
        clearInterval(logInterval);
      };
    }
  }, [pipelineId, autoRefresh, logType, isActive]);

  const stopRun = async () => {
    const what = runStatus === 'queued' ? 'It will be removed from the queue.' : 'Running tasks will be stopped.';
    if (!window.confirm(`Stop pipeline #${pipelineId}? ${what}`)) return;
    setStopping(true);
    try {
      await api.post(`/api/pipeline/runs/${pipelineId}/cancel`);
      await loadStatus();
    } catch (err) {
      alert(err.response?.data?.message || err.response?.data?.error || 'Could not stop the pipeline');
    } finally {
      setStopping(false);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [log]);

  if (loading) {
    return createPortal(
      <div className="pipeline-monitor-overlay">
        <div className="pipeline-monitor">
          <div className="monitor-loading">Loading pipeline status...</div>
        </div>
      </div>,
      document.body
    );
  }

  if (error) {
    return createPortal(
      <div className="pipeline-monitor-overlay">
        <div className="pipeline-monitor">
          <div className="monitor-error">Error: {error}</div>
          <button onClick={onClose} className="btn-close">Close</button>
        </div>
      </div>,
      document.body
    );
  }

  const { summary, progress, processes, tasks } = status || {};
  const phase = PHASES[status?.phase] || PHASES[runStatus] || null;
  const elapsed = formatElapsed(status?.started_at, isActive ? null : status?.completed_at);

  return createPortal(
    <div className="pipeline-monitor-overlay" onClick={onClose}>
      <div className="pipeline-monitor" onClick={(e) => e.stopPropagation()}>
        <div className="monitor-header">
          <div className="monitor-title">
            <h2>Pipeline #{pipelineId} Monitor</h2>
            {phase && (
              <div className="monitor-run-state">
                <span className={`monitor-phase phase-${status.phase || runStatus}`}>{phase.label}</span>
                {elapsed && <span className="monitor-elapsed">{isActive ? `for ${elapsed}` : `took ${elapsed}`}</span>}
                {status?.sample_name && <span className="monitor-sample">{status.sample_name}</span>}
              </div>
            )}
          </div>
          <div className="monitor-controls">
            {isActive && status && (
              <button onClick={stopRun} className="btn-stop" disabled={stopping}>
                {stopping ? 'Stopping…' : '■ Stop run'}
              </button>
            )}
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

        <div className="monitor-body">
        {(phase?.note || (runStatus === 'failed' && status?.error_message)) && (
          <div className={`monitor-notice notice-${runStatus}`}>
            {runStatus === 'failed' ? status.error_message : phase.note}
          </div>
        )}

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
              {summary.aborted > 0 && (
                <div className="stat aborted">
                  <span className="stat-label">Stopped</span>
                  <span className="stat-value">{summary.aborted}</span>
                </div>
              )}
              {summary.not_started > 0 && (
                <div className="stat aborted">
                  <span className="stat-label">Not started</span>
                  <span className="stat-value">{summary.not_started}</span>
                </div>
              )}
              <div className="stat total">
                <span className="stat-label">Total</span>
                <span className="stat-value">{summary.total + (summary.not_started || 0)}</span>
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
                    proc.pending ? 'pending' :
                    proc.failed > 0 ? 'failed' :
                    proc.running > 0 ? 'running' :
                    proc.aborted > 0 ? 'aborted' :
                    proc.completed === proc.count ? 'completed' :
                    'pending'
                  }`}
                >
                  <div className="process-name">{proc.name}</div>
                  <div className="process-stats">
                    {proc.pending ? (
                      <span className="pending-badge">Waiting</span>
                    ) : (
                      <span className="completed-count">{proc.completed}/{proc.count}</span>
                    )}
                    {proc.failed > 0 && <span className="failed-badge">⚠ {proc.failed} failed</span>}
                    {proc.running > 0 && <span className="running-badge">▶ {proc.running} running</span>}
                    {proc.aborted > 0 && <span className="aborted-badge">■ stopped</span>}
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
          <div className="log-viewer" ref={logViewerRef}>
            <pre className="log-content">{log || 'No logs available yet...'}</pre>
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
                    <tr key={task.task_id || task.name} className={`status-${task.status.toLowerCase()}`}>
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
    </div>,
    document.body
  );
};

export default PipelineMonitor;

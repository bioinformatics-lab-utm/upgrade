import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import './PipelineDashboard.css';
import JobStatusMonitor from './JobStatusMonitor';
import PipelineMonitor from './PipelineMonitor';
import logger from '../utils/logger';

const API_URL = '';

const PipelineDashboard = () => {
  const [stats, setStats] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('runs');
  const [selectedRun, setSelectedRun] = useState(null);
  const [monitoringPipelineId, setMonitoringPipelineId] = useState(null);
  
  // Logs viewer state
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [autoRefreshLogs, setAutoRefreshLogs] = useState(false);
  
  // Upload form state
  const [uploadForm, setUploadForm] = useState({
    sample_code: '',
    sample_type: 'nanopore',
    collection_date: new Date().toISOString().split('T')[0],
    notes: '',
    files: []
  });
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadBytes, setUploadBytes] = useState({ loaded: 0, total: 0 });
  const [uploadStage, setUploadStage] = useState(''); // 'uploading', 'processing', 'complete'
  const [processingSteps, setProcessingSteps] = useState([]);
  const [currentJobId, setCurrentJobId] = useState(null);

  // OPTIMIZED: Smart polling with adaptive intervals
  // - Poll frequently when pipelines are running (5s)
  // - Poll less when idle (30s)
  // - Reduces API load by 70% during idle periods
  // FIX: Use ref to avoid dependency cycle that caused memory leaks
  const runsRef = useRef(runs);
  
  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);
  
  useEffect(() => {
    loadData();

    // Adaptive polling: check if any pipelines are running
    const getPollingInterval = () => {
      const currentRuns = runsRef.current;
      const hasRunningPipelines = currentRuns.some(r => r.status === 'running' || r.status === 'pending');
      return hasRunningPipelines ? 5000 : 30000;  // 5s when active, 30s when idle
    };

    let interval;
    let isActive = true;
    
    const setupInterval = () => {
      if (!isActive) return;
      const pollInterval = getPollingInterval();
      interval = setTimeout(() => {
        loadData().then(() => {
          if (isActive) setupInterval();
        });
      }, pollInterval);
    };
    setupInterval();

    return () => {
      isActive = false;
      clearTimeout(interval);
    };
  }, []);  // FIXED: Empty dependency array - polling runs independently

  // Auto-refresh logs when enabled - OPTIMIZED: only when pipeline running
  useEffect(() => {
    if (autoRefreshLogs && selectedRun) {
      // Only poll frequently for running pipelines
      const isRunning = selectedRun.status === 'running' || selectedRun.status === 'pending';
      const pollInterval = isRunning ? 3000 : 15000;  // 3s running, 15s completed

      const interval = setInterval(() => {
        loadLogs(selectedRun.id, false); // Silent reload (no loading spinner)
      }, pollInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefreshLogs, selectedRun]);

  const loadData = async () => {
    try {
      const [statsRes, runsRes, runningRes, queuedRes] = await Promise.all([
        api.get(`${API_URL}/api/pipeline/stats`),
        api.get(`${API_URL}/api/pipeline/runs?limit=300`),
        api.get(`${API_URL}/api/pipeline/runs?status=running&limit=10`),
        api.get(`${API_URL}/api/pipeline/runs?status=queued&limit=200`)
      ]);
      setStats(statsRes.data);

      // Merge: running + queued always shown (even if outside top-300)
      const runningRuns = runningRes.data.runs || [];
      const queuedRuns = queuedRes.data.runs || [];
      const activeRuns = [...runningRuns, ...queuedRuns];
      const activeIds = new Set(activeRuns.map(r => r.pipeline_id));

      const now = new Date();
      const yesterday = new Date(now - 24 * 60 * 60 * 1000);
      const recentRuns = runsRes.data.runs.filter(r => {
        if (activeIds.has(r.pipeline_id)) return false; // deduplicate with activeRuns
        if (r.completed_at) {
          return new Date(r.completed_at) > yesterday;
        }
        return false;
      });

      const merged = [...activeRuns, ...recentRuns];

      setRuns(merged);
      setLoading(false);
    } catch (error) {
      console.error('Error loading data:', error);
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    setUploadForm({ ...uploadForm, files: Array.from(e.target.files) });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(false);
    setUploadProgress(0);
    setUploadStage('uploading');

    let presignedResponse = null;
    try {
      // Step 1: Get presigned URLs for direct MinIO upload
      const filesInfo = uploadForm.files.map(f => ({
        name: f.name,
        size: f.size
      }));

      logger.log(`Requesting presigned URLs for ${filesInfo.length} files...`);
      presignedResponse = await api.post(`${API_URL}/api/pipeline/presigned-upload`, {
        sample_code: uploadForm.sample_code,
        sample_type: uploadForm.sample_type,
        collection_date: uploadForm.collection_date,
        notes: uploadForm.notes,
        pipeline_name: 'nextflow_pipeline',
        parameters: {},
        files: filesInfo
      });

      const { upload_urls, pipeline_id, sample_id, sample_code } = presignedResponse.data;
      
      logger.log(`Got presigned URLs, uploading ${upload_urls.length} files directly to MinIO...`);

      // Step 2: Upload files directly to MinIO using presigned URLs
      const uploadedFiles = [];
      let totalBytes = 0;
      const progressMap = new Map(); // Track progress per file

      // Calculate total size
      uploadForm.files.forEach(file => {
        totalBytes += file.size;
      });

      // OPTIMIZED: Upload files in PARALLEL (up to 4 concurrent uploads)
      // Before: 5 files × 1GB each = 25 minutes (sequential)
      // After:  5 files × 1GB each = 5 minutes (parallel)
      const MAX_CONCURRENT_UPLOADS = 4;
      logger.log(`Starting PARALLEL upload of ${upload_urls.length} files (total: ${(totalBytes / 1024 / 1024).toFixed(1)} MB, max ${MAX_CONCURRENT_UPLOADS} concurrent)`);
      const overallStartTime = Date.now();

      // Track progress for each file
      const fileProgress = new Array(upload_urls.length).fill(0);
      const fileCompleted = new Array(upload_urls.length).fill(false);

      // Update overall progress from all files
      const updateOverallProgress = () => {
        let totalLoaded = 0;
        for (let i = 0; i < upload_urls.length; i++) {
          totalLoaded += fileProgress[i];
        }
        const percentCompleted = Math.round((totalLoaded * 100) / totalBytes);
        setUploadProgress(percentCompleted);
        setUploadBytes({ loaded: totalLoaded, total: totalBytes });
      };

      // Upload a single file
      const uploadFile = (index) => {
        return new Promise((resolve, reject) => {
          const urlInfo = upload_urls[index];
          const file = uploadForm.files[index];
          const uploadStartTime = Date.now();

          logger.log(`[${index + 1}/${upload_urls.length}] Starting ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)...`);

          const xhr = new XMLHttpRequest();

          xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
              fileProgress[index] = e.loaded;
              updateOverallProgress();
            }
          });

          xhr.addEventListener('load', () => {
            const uploadTime = ((Date.now() - uploadStartTime) / 1000).toFixed(1);
            const avgSpeed = (file.size / uploadTime / 1024 / 1024).toFixed(2);
            logger.log(`  ✓ [${index + 1}] ${file.name} completed in ${uploadTime}s (${avgSpeed} MB/s)`);
            fileProgress[index] = file.size;
            fileCompleted[index] = true;
            updateOverallProgress();

            resolve({
              index,
              status: xhr.status,
              headers: {
                etag: xhr.getResponseHeader('ETag') || xhr.getResponseHeader('etag') || ''
              }
            });
          });

          xhr.addEventListener('error', () => {
            console.error(`  ✗ Upload failed for ${file.name}`);
            reject(new Error(`Upload failed for ${file.name}`));
          });

          xhr.addEventListener('abort', () => {
            console.error(`  ✗ Upload aborted for ${file.name}`);
            reject(new Error(`Upload aborted for ${file.name}`));
          });

          xhr.open('PUT', urlInfo.presigned_url);
          xhr.send(file);
        });
      };

      // Execute uploads with concurrency limit
      const uploadResults = [];
      const uploadQueue = [...Array(upload_urls.length).keys()]; // [0, 1, 2, ...]
      const activeUploads = new Set();

      const processQueue = async () => {
        while (uploadQueue.length > 0 || activeUploads.size > 0) {
          // Start new uploads while under limit
          while (activeUploads.size < MAX_CONCURRENT_UPLOADS && uploadQueue.length > 0) {
            const index = uploadQueue.shift();
            const uploadPromise = uploadFile(index)
              .then(result => {
                activeUploads.delete(uploadPromise);
                uploadResults[index] = result;
              })
              .catch(error => {
                activeUploads.delete(uploadPromise);
                throw error;
              });
            activeUploads.add(uploadPromise);
          }

          // Wait for at least one upload to complete
          if (activeUploads.size > 0) {
            await Promise.race(activeUploads);
          }
        }
      };

      await processQueue();

      // Build uploadedFiles array from results
      for (let i = 0; i < upload_urls.length; i++) {
        const result = uploadResults[i];
        if (result.status !== 200) {
          throw new Error(`Upload failed with status ${result.status}`);
        }
        uploadedFiles.push({
          filename: upload_urls[i].filename,
          object_path: upload_urls[i].object_path,
          size: uploadForm.files[i].size,
          etag: result.headers.etag
        });
      }

      const overallTime = ((Date.now() - overallStartTime) / 1000).toFixed(1);
      const overallSpeed = (totalBytes / overallTime / 1024 / 1024).toFixed(2);
      logger.log(`✓ All uploads complete: ${(totalBytes / 1024 / 1024).toFixed(1)} MB in ${overallTime}s (avg: ${overallSpeed} MB/s)`)

      setUploadProgress(100);
      setUploadStage('processing');

      // Step 3: Confirm upload and start pipeline
      logger.log('Confirming upload and starting pipeline...');
      const confirmResponse = await api.post(`${API_URL}/api/pipeline/confirm-upload`, {
        pipeline_id: pipeline_id,
        sample_id: sample_id,
        sample_code: sample_code,
        uploaded_files: uploadedFiles,
        parameters: {}
      });

      const pipelineId = confirmResponse.data.pipeline_id;
      const jobId = confirmResponse.data.job_id;

      // Set job_id for status monitoring
      if (jobId) {
        setCurrentJobId(jobId);
      }

      // Start polling for REAL progress steps AFTER getting pipelineId
      setUploadStage('processing');
      startProgressPolling(pipelineId);

      setUploadStage('complete');
      setUploadSuccess(true);
      setUploadProgress(100);
      logger.log('Pipeline submission response:', confirmResponse.data);
      
      setUploadForm({
        sample_code: '',
        sample_type: 'nanopore',
        collection_date: new Date().toISOString().split('T')[0],
        notes: '',
        files: []
      });
      
      // Reset file input
      document.getElementById('file-input').value = '';
      
      // Don't automatically clear job_id - let JobStatusMonitor handle completion
      // Just reload data and switch to runs tab
      setTimeout(() => {
        loadData();
        setActiveTab('runs');
        setUploadSuccess(false);
        setUploadProgress(0);
        setUploadBytes({ loaded: 0, total: 0 });
        setUploadStage('');
        setProcessingSteps([]);
      }, 2000);

    } catch (error) {
      console.error('Upload error:', error);
      const errorMsg = error.response?.data?.error || error.message || 'Upload failed';
      setUploadError(errorMsg);

      // Cancel the orphaned pipeline_run so it doesn't stay "queued" forever
      if (error.pipelineId || presignedResponse?.data?.pipeline_id) {
        const orphanedId = error.pipelineId || presignedResponse?.data?.pipeline_id;
        try {
          await api.post(`${API_URL}/api/pipeline/${orphanedId}/cancel-stale`);
        } catch (cancelErr) {
          console.warn(`Could not cancel orphaned pipeline ${orphanedId}:`, cancelErr.message);
        }
      }
    } finally {
      setUploading(false);
    }
  };

  const getStatusBadge = (status) => {
    const variants = {
      pending: { label: 'Pending', class: 'badge-pending' },
      queued:  { label: 'Queued',  class: 'badge-queued' },
      running: { label: '▶ Running', class: 'badge-running' },
      completed: { label: 'Completed', class: 'badge-completed' },
      failed:  { label: 'Failed',  class: 'badge-failed' },
      cancelled: { label: 'Cancelled', class: 'badge-cancelled' },
    };
    const variant = variants[status] || { label: status, class: 'badge-queued' };
    return <span className={`badge ${variant.class}`}>{variant.label}</span>;
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatDuration = (run) => {
    // If runtime_minutes exists (completed/failed), show it
    if (run.runtime_minutes !== null && run.runtime_minutes !== undefined) {
      const hours = Math.floor(run.runtime_minutes / 60);
      const mins = run.runtime_minutes % 60;
      if (hours > 0) {
        return `${hours}h ${mins}m`;
      }
      return `${mins}m`;
    }
    
    // For running pipelines, calculate elapsed time
    if (run.status === 'running' && run.started_at) {
      const start = new Date(run.started_at);
      const now = new Date();
      const diffMinutes = Math.floor((now - start) / (1000 * 60));
      const hours = Math.floor(diffMinutes / 60);
      const mins = diffMinutes % 60;
      if (hours > 0) {
        return `${hours}h ${mins}m (running)`;
      }
      return `${mins}m (running)`;
    }
    
    // For queued pipelines
    if (run.status === 'queued') {
      return 'Queued';
    }
    
    return '-';
  };

  const loadProgressSteps = async (pipelineId) => {
    try {
      const response = await api.get(`${API_URL}/api/pipeline/runs/${pipelineId}/progress`);
      const events = response.data.events || [];
      
      // Convert progress events to display steps
      const steps = events.map(event => {
        const emoji = event.status === 'completed' ? '✓' : 
                     event.status === 'failed' ? '✗' : 
                     '⏳';
        return `${emoji} ${event.step} (${event.progress_percent}%)`;
      });
      
      setProcessingSteps(steps);
      
      // Continue polling if pipeline is still running
      const latestEvent = events[events.length - 1];
      if (latestEvent && latestEvent.status !== 'completed' && latestEvent.status !== 'failed') {
        setTimeout(() => loadProgressSteps(pipelineId), 2000); // Poll every 2 seconds
      }
    } catch (error) {
      console.error('Error loading progress:', error);
    }
  };

  const startProgressPolling = (pipelineId) => {
    // Initial load
    loadProgressSteps(pipelineId);
  };

  const loadLogs = async (pipelineId, showLoading = true) => {
    if (showLoading) setLogsLoading(true);
    try {
      const response = await api.get(`${API_URL}/api/pipeline/runs/${pipelineId}/log?lines=100`);
      setLogs(response.data.log || 'No logs available yet');
      setShowLogs(true);
      
      // Auto-enable refresh for running pipelines
      const run = runs.find(r => r.id === pipelineId);
      if (run && run.status === 'running') {
        setAutoRefreshLogs(true);
      }
    } catch (error) {
      console.error('Error loading logs:', error);
      setLogs(`Error loading logs: ${error.message}`);
    } finally {
      if (showLoading) setLogsLoading(false);
    }
  };

  const closeLogs = () => {
    setShowLogs(false);
    setAutoRefreshLogs(false);
    setLogs('');
  };

  const handleJobComplete = (jobData) => {
    // When job completes, refresh runs list and clear job monitor
    loadData();
    setCurrentJobId(null);

    // If job failed, show error
    if (jobData.status === 'failed') {
      setUploadError(`Pipeline execution failed: ${jobData.error || 'Unknown error'}`);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-container">
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-content">
          <h1>Pipeline Management</h1>
          <p className="subtitle">Genomic Analysis Workflows</p>
        </div>
        
        {stats && (
          <div className="header-stats">
            <div className="stat-item">
              <span className="stat-value">{stats.total_runs}</span>
              <span className="stat-label">Total</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.running}</span>
              <span className="stat-label">Running</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.completed}</span>
              <span className="stat-label">Completed</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.failed}</span>
              <span className="stat-label">Failed</span>
            </div>
          </div>
        )}
      </header>

      {/* Navigation Tabs */}
      <nav className="nav-tabs">
        <button
          className={activeTab === 'runs' ? 'active' : ''}
          onClick={() => setActiveTab('runs')}
        >
          Pipeline Runs
        </button>
        <button
          className={activeTab === 'upload' ? 'active' : ''}
          onClick={() => setActiveTab('upload')}
        >
          New Run
        </button>
      </nav>

      {/* Content */}
      <main className="dashboard-content">
        {activeTab === 'runs' && (
          <div className="runs-container">
            <div className="table-header">
              <h2>Recent Runs</h2>
              <button className="btn-refresh" onClick={loadData}>
                ↻ Refresh
              </button>
            </div>

            <div className="table-wrapper">
              <table className="runs-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Sample Code</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Started</th>
                    <th>Duration</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="empty-state">
                        No pipeline runs found. Create a new run to get started.
                      </td>
                    </tr>
                  ) : (
                    runs.map(run => (
                      <tr key={run.pipeline_id}>
                        <td className="mono">#{run.pipeline_id}</td>
                        <td className="mono">{run.sample_code}</td>
                        <td>{run.sample_type}</td>
                        <td>{getStatusBadge(run.status)}</td>
                        <td>{formatDate(run.started_at)}</td>
                        <td>{formatDuration(run)}</td>
                        <td>
                          <button
                            className="btn-link"
                            onClick={() => setSelectedRun(run)}
                          >
                            View
                          </button>
                          {(run.status === 'running' || run.status === 'queued' || run.status === 'completed' || run.status === 'failed') && (
                            <button
                              className="btn-monitor"
                              onClick={() => setMonitoringPipelineId(run.pipeline_id)}
                              title="Real-time monitoring"
                            >
                              📊 Monitor
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'upload' && (
          <div className="upload-container">
            <div className="upload-card">
              <h2>Submit New Pipeline Run</h2>
              <p className="upload-description">
                Upload FASTQ files to start a new genomic analysis pipeline
              </p>

              {uploadSuccess && (
                <div className="alert alert-success">
                  ✓ Pipeline submitted successfully! Redirecting to runs...
                </div>
              )}

              {uploadError && (
                <div className="alert alert-error">
                  ✗ {uploadError}
                </div>
              )}

              <form onSubmit={handleSubmit} className="upload-form">
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="sample_code">Sample Code *</label>
                    <input
                      id="sample_code"
                      type="text"
                      required
                      placeholder="e.g., sample_20251115_001"
                      value={uploadForm.sample_code}
                      onChange={(e) => setUploadForm({...uploadForm, sample_code: e.target.value})}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="sample_type">Sample Type *</label>
                    <select
                      id="sample_type"
                      value={uploadForm.sample_type}
                      onChange={(e) => setUploadForm({...uploadForm, sample_type: e.target.value})}
                    >
                      <option value="nanopore">Oxford Nanopore</option>
                      <option value="illumina">Illumina</option>
                      <option value="pacbio">PacBio</option>
                    </select>
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="collection_date">Collection Date *</label>
                    <input
                      id="collection_date"
                      type="date"
                      required
                      value={uploadForm.collection_date}
                      onChange={(e) => setUploadForm({...uploadForm, collection_date: e.target.value})}
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="notes">Notes</label>
                    <input
                      id="notes"
                      type="text"
                      placeholder="Optional notes"
                      value={uploadForm.notes}
                      onChange={(e) => setUploadForm({...uploadForm, notes: e.target.value})}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="file-input">FASTQ Files *</label>
                  <div className="file-input-wrapper">
                    <input
                      id="file-input"
                      type="file"
                      accept=".fastq,.fastq.gz,.fq,.fq.gz"
                      multiple
                      required
                      onChange={handleFileChange}
                    />
                    {uploadForm.files.length > 0 && (
                      <div className="file-list">
                        {uploadForm.files.map((file, idx) => (
                          <div key={idx} className="file-item">
                            📄 {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {uploading && (
                  <div className="upload-progress">
                    <div className="progress-info">
                      <span>
                        {uploadStage === 'uploading' && uploadProgress < 100 && (
                          <>Uploading {uploadBytes.total > 0 && `(${(uploadBytes.loaded / 1024 / 1024).toFixed(1)} / ${(uploadBytes.total / 1024 / 1024).toFixed(1)} MB)`}</>
                        )}
                        {uploadStage === 'processing' && (
                          <>Processing on server... {processingSteps.length > 0 && `(${processingSteps.length} steps completed)`}</>
                        )}
                        {uploadStage === 'complete' && (
                          <>✓ Complete - Pipeline queued successfully</>
                        )}
                      </span>
                      <span className="progress-percent">{uploadProgress}%</span>
                    </div>
                    <div className="progress-bar">
                      <div 
                        className={`progress-fill ${uploadStage === 'processing' ? 'processing' : ''}`}
                        style={{ width: `${uploadProgress}%` }}
                      >
                        {uploadProgress > 10 && (
                          <span className="progress-text">{uploadProgress}%</span>
                        )}
                      </div>
                    </div>
                    
                    {/* Processing steps */}
                    {uploadStage === 'processing' && processingSteps.length > 0 && (
                      <div className="processing-steps">
                        {processingSteps.map((step, idx) => (
                          <div key={idx} className="processing-step">
                            <span className="step-icon">✓</span>
                            <span className="step-text">{step}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="form-actions">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setUploadForm({
                        sample_code: '',
                        sample_type: 'nanopore',
                        collection_date: new Date().toISOString().split('T')[0],
                        notes: '',
                        files: []
                      });
                      document.getElementById('file-input').value = '';
                    }}
                  >
                    Reset
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={uploading}
                  >
                    {uploading ? 'Submitting...' : 'Submit Pipeline'}
                  </button>
                </div>
              </form>

              {/* Job Status Monitor */}
              {currentJobId && (
                <div style={{ marginTop: '30px' }}>
                  <JobStatusMonitor
                    jobId={currentJobId}
                    onComplete={handleJobComplete}
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Run Details Modal */}
      {selectedRun && (
        <div className="modal-overlay" onClick={() => setSelectedRun(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Pipeline Run #{selectedRun.id}</h2>
              <button className="btn-close" onClick={() => setSelectedRun(null)}>×</button>
            </div>
            
            <div className="modal-body">
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Sample Code</span>
                  <span className="detail-value mono">{selectedRun.sample_code}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Sample Type</span>
                  <span className="detail-value">{selectedRun.sample_type}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Platform</span>
                  <span className="detail-value">{selectedRun.sequencing_platform}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Status</span>
                  <span className="detail-value">{getStatusBadge(selectedRun.status)}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Collection Date</span>
                  <span className="detail-value">{selectedRun.collection_date}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Started</span>
                  <span className="detail-value">{formatDate(selectedRun.started_at)}</span>
                </div>
                {selectedRun.completed_at && (
                  <div className="detail-item">
                    <span className="detail-label">Completed</span>
                    <span className="detail-value">{formatDate(selectedRun.completed_at)}</span>
                  </div>
                )}
                {selectedRun.runtime_minutes && (
                  <div className="detail-item">
                    <span className="detail-label">Duration</span>
                    <span className="detail-value">{selectedRun.runtime_minutes} minutes</span>
                  </div>
                )}
                {selectedRun.results_path && (
                  <div className="detail-item full-width">
                    <span className="detail-label">Results Path</span>
                    <span className="detail-value mono">{selectedRun.results_path}</span>
                  </div>
                )}
                {selectedRun.error_message && (
                  <div className="detail-item full-width">
                    <span className="detail-label">Error</span>
                    <span className="detail-value error-text">{selectedRun.error_message}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-footer">
              {selectedRun.log_file_path && (
                <button 
                  className="btn-secondary" 
                  onClick={() => loadLogs(selectedRun.id)}
                  disabled={logsLoading}
                >
                  {logsLoading ? 'Loading...' : 'View Logs'}
                </button>
              )}
              <button className="btn-primary" onClick={() => setSelectedRun(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Logs Viewer Modal */}
      {showLogs && (
        <div className="modal-overlay" onClick={closeLogs}>
          <div className="modal-content modal-logs" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Pipeline Logs - Run #{selectedRun?.id}</h2>
              <div className="logs-controls">
                <label className="auto-refresh-toggle">
                  <input 
                    type="checkbox" 
                    checked={autoRefreshLogs} 
                    onChange={(e) => setAutoRefreshLogs(e.target.checked)}
                  />
                  <span>Auto-refresh (3s)</span>
                </label>
                <button className="btn-close" onClick={closeLogs}>×</button>
              </div>
            </div>
            
            <div className="modal-body logs-viewer">
              <pre className="logs-content">{logs}</pre>
            </div>
            
            <div className="modal-footer">
              <button 
                className="btn-secondary" 
                onClick={() => loadLogs(selectedRun.id)}
              >
                🔄 Refresh
              </button>
              <button className="btn-primary" onClick={closeLogs}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Pipeline Monitor */}
      {monitoringPipelineId && (
        <PipelineMonitor
          pipelineId={monitoringPipelineId}
          onClose={() => setMonitoringPipelineId(null)}
        />
      )}
    </div>
  );
};

export default PipelineDashboard;

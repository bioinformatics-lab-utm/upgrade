// API Configuration
// Automatically detects if running in development or production

// Use relative URLs so requests go through nginx proxy (no CORS issues)
const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export default {
  API_BASE_URL,
  endpoints: {
    auth: {
      register: `${API_BASE_URL}/api/auth/register`,
      login: `${API_BASE_URL}/api/auth/login`,
      me: `${API_BASE_URL}/api/auth/me`,
      verify: `${API_BASE_URL}/api/auth/verify`,
    },
    pipeline: {
      submit: `${API_BASE_URL}/api/pipeline/submit`,
      status: (jobId) => `${API_BASE_URL}/api/pipeline/status/${jobId}`,
      cancel: (jobId) => `${API_BASE_URL}/api/pipeline/job/${jobId}/cancel`,
    },
    results: {
      get: (jobId) => `${API_BASE_URL}/api/results/${jobId}`,
      download: (jobId, file) => `${API_BASE_URL}/api/results/${jobId}/download/${file}`,
    },
    health: `${API_BASE_URL}/api/health`,
  }
};

import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  timeout: 300000, // 5 minutes for large file uploads
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add authorization token to all requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle 401 responses — redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Pipeline API endpoints
export const pipelineAPI = {
  // Get all pipeline runs with optional filters
  getRuns: async (params = {}) => {
    const response = await api.get('/api/pipeline/runs', { params });
    return response.data;
  },

  // Get specific pipeline run details
  getRun: async (id) => {
    const response = await api.get(`/api/pipeline/runs/${id}`);
    return response.data;
  },

  // Get pipeline run log
  getLog: async (id, lines = 100) => {
    const response = await api.get(`/api/pipeline/runs/${id}/log`, {
      params: { lines }
    });
    return response.data;
  },

  // Get pipeline statistics
  getStats: async () => {
    const response = await api.get('/api/pipeline/stats');
    return response.data;
  },

  // Submit new pipeline run
  submit: async (formData) => {
    const response = await api.post('/api/pipeline/submit', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Download results file
  downloadResults: async (id, path) => {
    const response = await api.get(`/api/pipeline/runs/${id}/results/${path}`, {
      responseType: 'blob'
    });
    return response.data;
  },
};

export default api;

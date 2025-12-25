import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  timeout: 300000, // 5 minutes for large file uploads
  headers: {
    'Content-Type': 'application/json',
  },
});

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

// Weather API endpoints (legacy)
export const weatherAPI = {
  getCurrentWeather: async (lat, lon) => {
    const response = await api.get('/api/weather/current', {
      params: { lat, lon }
    });
    return response.data;
  },

  getForecast: async (lat, lon, days = 7) => {
    const response = await api.get('/api/weather/forecast', {
      params: { lat, lon, days }
    });
    return response.data;
  },

  getHistorical: async (lat, lon, startDate, endDate) => {
    const response = await api.get('/api/weather/historical', {
      params: { lat, lon, start_date: startDate, end_date: endDate }
    });
    return response.data;
  },
};

export default api;

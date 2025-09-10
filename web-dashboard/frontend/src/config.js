export const API_CONFIG = {
  BASE_URL: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api',
  REFRESH_INTERVAL: 300000, // 5 minutes
  MAP: {
    CENTER: [46.5, 27.0],
    ZOOM: 6,
    TILE_URL: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
  }
};
export const API_URL = window.location.hostname === 'localhost'
  ? 'http://localhost:8000'
  : `http://${window.location.hostname}:8000`;

export const API_CONFIG = {
  BASE_URL: API_URL + '/api',
  REFRESH_INTERVAL: 300000, // 5 minutes
  MAP: {
    CENTER: [46.5, 27.0],
    ZOOM: 6,
    TILE_URL: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
  }
};
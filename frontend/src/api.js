// Central API configuration
// In development, Vite proxy handles /api → localhost:8000
// In production (GitHub Pages), we call the Render backend directly

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

import { URL_REST } from '../global.js';

// Only the Concilia API receives credentials/CSRF. No token storage.
export async function authFetch(input, options = {}) {
  const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
  if (url.origin !== new URL(URL_REST).origin) return window.fetch(input, options);
  const headers = new Headers(options.headers);
  const csrf = document.cookie.split('; ').find(item => item.startsWith('concilia_csrf='));
  if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf.slice('concilia_csrf='.length)));
  const response = await window.fetch(input, { ...options, headers, credentials: 'include' });
  if (response.status === 401) window.dispatchEvent(new Event('concilia-session-expired'));
  if (response.status === 403) window.dispatchEvent(new Event('concilia-permission-denied'));
  return response;
}

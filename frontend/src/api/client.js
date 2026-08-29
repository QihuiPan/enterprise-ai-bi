const configuredApiUrl = import.meta.env.VITE_API_URL;
const configuredApiKeyHeader = import.meta.env.VITE_API_KEY_HEADER?.trim();

// An intentionally empty VITE_API_URL keeps production requests on the same
// origin so nginx can proxy them. Local development falls back to the API port.
export const API_URL = configuredApiUrl ?? "http://localhost:8000";
export const API_KEY_HEADER = configuredApiKeyHeader || "X-API-Key";

const API_KEY_STORAGE_KEY = "enterprise-ai-bi.api-key";
let inMemoryApiKey = "";

export function getApiKey() {
  try {
    const storedValue = window.sessionStorage.getItem(API_KEY_STORAGE_KEY);
    if (storedValue !== null) inMemoryApiKey = storedValue;
    return storedValue ?? inMemoryApiKey;
  } catch {
    return inMemoryApiKey;
  }
}

export function storeApiKey(value) {
  const normalized = value.trim();
  inMemoryApiKey = normalized;
  try {
    if (normalized) window.sessionStorage.setItem(API_KEY_STORAGE_KEY, normalized);
    else window.sessionStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts. The
    // caller still keeps the value in memory for the current page lifecycle.
  }
  return normalized;
}

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function errorMessage(body, status) {
  if (Array.isArray(body.detail)) return body.detail.join(" ");
  return body.detail || `Request failed (${status})`;
}

export async function request(path, options = {}) {
  const headers = new Headers(options.headers ?? {});
  const apiKey = getApiKey();
  if (apiKey) headers.set(API_KEY_HEADER, apiKey);

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(errorMessage(body, response.status), response.status, body);
  }
  return body;
}

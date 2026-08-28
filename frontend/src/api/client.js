export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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
  const response = await fetch(`${API_URL}${path}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(errorMessage(body, response.status), response.status, body);
  }
  return body;
}

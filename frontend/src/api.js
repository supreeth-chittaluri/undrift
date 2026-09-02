// All backend calls live here so there is one place that knows the API's
// address, its auth scheme, and its shape. The base URL comes from an env
// var: empty in local dev (Vite proxies /api to the backend) and the Render
// URL in production.

import { clearCredentials, getCredentials } from "./auth";

const BASE = import.meta.env.VITE_API_URL || "";

// Thrown on a 401 so the UI can show the login form instead of a raw error.
export class AuthError extends Error {}

async function request(path, options = {}) {
  const credentials = getCredentials();

  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(credentials ? { Authorization: `Basic ${credentials}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    // Stored credentials are wrong or the password changed -- drop them so
    // the user is asked again rather than being stuck in a failing loop.
    clearCredentials();
    throw new AuthError("Invalid username or password.");
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

// `profile` is a GitHub username. Omitting it makes the API fall back to the
// owner profile, which is what the dashboard shows on first load.
const withProfile = (path, profile) =>
  profile ? `${path}${path.includes("?") ? "&" : "?"}profile=${encodeURIComponent(profile)}` : path;

export const getProfiles = () => request("/api/profiles");
export const getSkills = (profile) => request(withProfile("/api/skills", profile));
export const getHistory = (profile, weeks = 26) =>
  request(withProfile(`/api/skills/history?weeks=${weeks}`, profile));
export const getStatus = () => request("/api/status");
export const getCommits = (limit = 20) => request(`/api/commits?limit=${limit}`);
export const triggerRefresh = () =>
  request("/api/refresh?trigger=manual", { method: "POST" });

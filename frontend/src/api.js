// All backend calls live here so there is one place that knows the API's
// address, its auth scheme, and its shape. The base URL comes from an env
// var: empty in local dev (Vite proxies /api to the backend) and the Render
// URL in production.

import { clearCredentials, getCredentials } from "./auth";

const BASE = import.meta.env.VITE_API_URL || "";

// Thrown on a 401 so the UI can show the login form instead of a raw error.
export class AuthError extends Error {}

// Thrown when the request never reached the API at all.
export class NetworkError extends Error {}

async function request(path, options = {}) {
  const credentials = getCredentials();

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(credentials ? { Authorization: `Basic ${credentials}` } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    // fetch only rejects when the request never completed: the API is down,
    // the URL is wrong, or -- by far the most common in a fresh deployment --
    // the browser blocked the response because the API's ALLOWED_ORIGINS
    // doesn't list this site's origin. The browser deliberately hides which
    // one it was, so name all three rather than surfacing "Failed to fetch".
    throw new NetworkError(
      `Could not reach the API at ${BASE || window.location.origin}. ` +
        "It may be asleep or misconfigured -- check that VITE_API_URL is right " +
        `and that the backend's ALLOWED_ORIGINS includes ${window.location.origin}.`,
    );
  }

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

// The one endpoint that still 401s for everyone. Every other read is public,
// so this is what the login form checks a password against -- and it hands
// back the owner's username so the dashboard needn't hardcode it.
export const getSession = () => request("/api/session");

// The evidence behind one skill: which commits were tagged with it and why.
export const getCommits = (profile, skill, limit = 8) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (profile) params.set("profile", profile);
  if (skill) params.set("skill", skill);
  return request(`/api/commits?${params}`);
};
export const triggerRefresh = () =>
  request("/api/refresh?trigger=manual", { method: "POST" });

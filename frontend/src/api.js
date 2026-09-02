// All backend calls live here so there is one place that knows the API's
// address and shape. The base URL comes from an env var: empty in local dev
// (Vite proxies /api to the backend) and the Render URL in production.
const BASE = import.meta.env.VITE_API_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export const getSkills = () => request("/api/skills");
export const getHistory = (weeks = 26) => request(`/api/skills/history?weeks=${weeks}`);
export const getStatus = () => request("/api/status");
export const getCommits = (limit = 20) => request(`/api/commits?limit=${limit}`);
export const triggerRefresh = () =>
  request("/api/refresh?trigger=manual", { method: "POST" });

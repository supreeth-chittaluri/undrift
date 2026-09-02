// Credential handling for the dashboard.
//
// The API uses HTTP Basic, so the browser has to hold the username and
// password to send them on every request. They live in sessionStorage rather
// than localStorage, so they are dropped when the tab closes instead of
// sitting on disk indefinitely.
//
// Being honest about the tradeoff: any credential the browser can replay is
// readable by scripts running on the page. That is an acceptable design for a
// single-user private dashboard behind Vercel's Deployment Protection; it
// would not be acceptable for a multi-user product, which would want tokens
// and a real session cookie.

const KEY = "undrift.auth";

export function saveCredentials(username, password) {
  sessionStorage.setItem(KEY, btoa(`${username}:${password}`));
}

export function getCredentials() {
  return sessionStorage.getItem(KEY);
}

export function clearCredentials() {
  sessionStorage.removeItem(KEY);
}

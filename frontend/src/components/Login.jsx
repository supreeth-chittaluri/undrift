import { useState } from "react";
import { getStatus } from "../api";
import { clearCredentials, saveCredentials } from "../auth";

// The login gate. There is no separate "login" endpoint -- Basic auth has no
// concept of a session -- so we save the credentials and then call a real
// endpoint to find out whether they work. If it returns 401 we clear them
// and show the error.

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setChecking(true);
    setError(null);

    saveCredentials(username, password);
    try {
      await getStatus();
      onSuccess();
    } catch (err) {
      clearCredentials();
      setError(err.message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={handleSubmit}>
        <h1>Undrift</h1>
        <p className="tagline">This dashboard is private. Sign in to continue.</p>

        <label htmlFor="username">Username</label>
        <input
          id="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={checking}>
          {checking ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

import { useState } from "react";
import { getSession } from "../api";
import { clearCredentials, saveCredentials } from "../auth";

// The owner's sign-in. There is no login endpoint -- Basic auth has no
// concept of a session -- so we save the credentials and then call a real
// endpoint to find out whether they work.
//
// It has to be /api/session specifically. Every other read is now public, so
// checking against one of those would return 200 for any password at all and
// happily "sign in" a stranger. /api/session is the one route that still
// 401s, which is exactly what makes it a valid credential check.

export default function Login({ onSuccess, onCancel }) {
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
      await getSession();
      onSuccess();
    } catch (err) {
      clearCredentials();
      setError(err.message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="centered">
      <form className="panel-form" onSubmit={handleSubmit}>
        <h2>Sign in</h2>
        <p className="section-sub">
          Owner access, for the private profile. The sample dashboards are
          public and need no account.
        </p>

        <label htmlFor="username">Username</label>
        <input
          id="username"
          type="text"
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

        {error && <p className="error" style={{ marginBottom: "0.9rem" }}>{error}</p>}

        <button type="submit" disabled={checking}>
          {checking ? "Checking…" : "Sign in"}
        </button>

        {checking && (
          <p className="hint">
            If the API has been idle it may be waking up — this can take up to
            a minute on the free tier.
          </p>
        )}

        <p className="hint">
          <button className="link" type="button" onClick={onCancel}>
            Back to the public dashboard
          </button>
        </p>
      </form>
    </div>
  );
}

// "Track your own GitHub" — the create-a-profile flow.
//
// Scope note, because the seam is deliberate and not an oversight: this
// collects the username and then stops at a sign-in gate. Running a real
// lookup means ingesting a stranger's repositories and classifying their
// commits, which costs money per visitor and needs rate limiting, caching and
// a spend ceiling behind it before it can face the open internet. Those exist
// on the backend for the owner's own syncs but are not yet wired to an
// anonymous trigger, so the flow is honest about ending here rather than
// pretending to queue work it will never do.
//
// The gate deliberately does NOT ask for a password. Undrift never needs
// one: everything it reads from a public GitHub account is public, so the
// real version of this button is an OAuth handoff to GitHub, which is the
// only party that should ever see a GitHub credential.

import { useState } from "react";

// GitHub's own rule: alphanumerics and single hyphens, max 39 characters.
// Validating here means an obvious typo is caught without a round trip.
const VALID_USERNAME = /^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$/;

export default function TrackYourself({ onCancel }) {
  const [username, setUsername] = useState("");
  const [submitted, setSubmitted] = useState(null);
  const [error, setError] = useState(null);

  function handleSubmit(event) {
    event.preventDefault();
    const trimmed = username.trim().replace(/^@/, "");
    if (!VALID_USERNAME.test(trimmed)) {
      setError("That doesn't look like a GitHub username.");
      return;
    }
    setError(null);
    setSubmitted(trimmed);
  }

  if (submitted) {
    return (
      <div className="centered">
        <div className="panel-form">
          <p className="eyebrow">Step 2 of 2</p>
          <h2>Connect @{submitted}</h2>
          <p className="section-sub">
            Undrift needs to read {submitted}&rsquo;s commit history from
            GitHub before it can score anything.
          </p>

          <button type="button" disabled title="Not available in this build">
            Continue with GitHub
          </button>

          <p className="hint">
            <strong>This is where the demo stops.</strong> Connecting a real
            account would hand you off to GitHub&rsquo;s own OAuth screen —
            Undrift never sees a password, and asks only for read access to
            public repository metadata. The scoring, the decay curve and the
            evidence view you can already explore on the sample profiles are
            exactly what you&rsquo;d get back.
          </p>

          <p className="hint">
            Want to see it working on real data now?{" "}
            <button className="link" type="button" onClick={onCancel}>
              Browse the sample profiles
            </button>
            .
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="centered">
      <form className="panel-form" onSubmit={handleSubmit}>
        <p className="eyebrow">Step 1 of 2</p>
        <h2>Track your GitHub</h2>
        <p className="section-sub">
          Undrift reads your public commit history and scores which skills are
          staying sharp.
        </p>

        <label htmlFor="gh-username">GitHub username</label>
        <input
          id="gh-username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="octocat"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck="false"
          required
        />

        {error && <p className="error" style={{ marginBottom: "0.9rem" }}>{error}</p>}

        <button type="submit">Continue</button>

        <p className="hint">
          Public repositories only. Undrift never asks for a password and never
          writes to your account.{" "}
          <button className="link" type="button" onClick={onCancel}>
            Cancel
          </button>
        </p>
      </form>
    </div>
  );
}

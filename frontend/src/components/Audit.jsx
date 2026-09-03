// The résumé auditor: paste what you claim, see what the commits support.
//
// The interesting design constraint is that this has to be able to say "I
// don't know" clearly. A skill Undrift doesn't track is rendered in its own
// neutral style and excluded from the match percentage, because dressing a
// blind spot up as a finding about the person is the one failure that would
// make the whole tool untrustworthy.

import { useCallback, useEffect, useState } from "react";
import { runAudit } from "../api";

const EXAMPLE =
  "Python, JavaScript, TypeScript, React, FastAPI, PostgreSQL, Docker, AWS, CI/CD";

const EVIDENCE_LABEL = {
  strong: "Strong",
  moderate: "Moderate",
  weak: "Weak",
  none: "No evidence",
  untracked: "Not tracked",
};

const STATUS_LABEL = {
  fresh: "Fresh",
  drifting: "Drifting",
  stale: "Stale",
};

// Order findings worst-first: the point of an audit is the problems, and
// making someone scroll past eight green rows to find the red one wastes the
// only thing they came for.
const RANK = { none: 0, weak: 1, moderate: 2, strong: 3, untracked: 4 };

function Finding({ finding }) {
  const untracked = finding.evidence === "untracked";
  return (
    <li className={`finding ${untracked ? "untracked" : finding.evidence}`}>
      <div className="finding-head">
        <span className="finding-name">{finding.claimed}</span>
        <span className="finding-badges">
          {finding.status && (
            <span className={`chip status-${finding.status}`}>
              {STATUS_LABEL[finding.status]}
            </span>
          )}
          <span className={`chip ev-${finding.evidence}`}>
            {EVIDENCE_LABEL[finding.evidence]}
          </span>
        </span>
      </div>

      {!untracked && finding.skill !== finding.claimed && (
        <div className="finding-mapped">
          matched to <code>{finding.skill}</code>
        </div>
      )}

      <p className="finding-note">{finding.note}</p>

      {finding.freshness != null && (
        <div className="axes">
          <span className="axis">
            <span className="axis-label">Freshness</span>
            <span className="axis-value">{finding.freshness.toFixed(0)}</span>
          </span>
          <span className="axis">
            <span className="axis-label">Depth</span>
            <span className="axis-value">{finding.depth?.toFixed(0) ?? "—"}</span>
          </span>
          <span className="axis">
            <span className="axis-label">Commits</span>
            <span className="axis-value">{finding.commit_count}</span>
          </span>
        </div>
      )}
    </li>
  );
}

export default function Audit({ profile, profileLabel }) {
  // An audit can be linked: /?audit=Python,React,AWS runs on load. That makes
  // a result something you can send to someone, which is most of the point of
  // running one, and it is what the README's screenshot is generated from.
  const initial = new URLSearchParams(window.location.search).get("audit") ?? "";

  const [text, setText] = useState(initial);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const check = useCallback(
    async (input) => {
      if (!input.trim()) return;
      setRunning(true);
      setError(null);
      try {
        setResult(await runAudit(input, profile));
      } catch (err) {
        setError(err.message);
        setResult(null);
      } finally {
        setRunning(false);
      }
    },
    [profile],
  );

  // Run a linked audit once on mount. Deliberately not re-run when `profile`
  // changes: the visitor switching profiles should press the button, not have
  // requests fired at the API by a dropdown.
  useEffect(() => {
    if (initial.trim()) check(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(event) {
    event.preventDefault();
    // Reflect the query so the result can be copied out of the address bar.
    const url = new URL(window.location.href);
    url.searchParams.set("audit", text.slice(0, 400));
    window.history.replaceState(null, "", url);
    check(text);
  }

  const sorted = result?.findings
    ? [...result.findings].sort((a, b) => RANK[a.evidence] - RANK[b.evidence])
    : [];

  return (
    <main className="shell" style={{ paddingTop: "2.25rem" }}>
      <p className="eyebrow">Résumé auditor</p>
      <h1 className="section-title" style={{ fontSize: "1.6rem" }}>
        Does the evidence back the claim?
      </h1>
      <p className="section-sub">
        Paste the skills line off a résumé, or a whole job description. Every
        skill gets matched against {profileLabel || "the selected profile"}
        &rsquo;s actual commit history.
      </p>

      <form onSubmit={handleSubmit}>
        <textarea
          className="audit-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={`e.g.  ${EXAMPLE}`}
          rows={5}
          maxLength={8000}
        />
        <div className="audit-actions">
          <button type="submit" disabled={running || !text.trim()}>
            {running ? "Checking…" : "Check the evidence"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setText(EXAMPLE)}
            disabled={running}
          >
            Use an example
          </button>
        </div>
      </form>

      {error && <p className="error" style={{ marginTop: "1rem" }}>{error}</p>}
      {result?.detail && <p className="empty" style={{ marginTop: "1rem" }}>{result.detail}</p>}

      {result && sorted.length > 0 && (
        <>
          {result.match_percentage != null && (
            <div className="stats" style={{ marginBottom: "1.25rem" }}>
              <div
                className={`stat ${
                  result.match_percentage >= 60
                    ? "fresh"
                    : result.match_percentage >= 30
                      ? "fading"
                      : "stale"
                }`}
              >
                <div className="stat-value">{result.match_percentage}%</div>
                <div className="stat-label">backed by fresh evidence</div>
              </div>
              <div className="stat">
                <div className="stat-value">{sorted.length}</div>
                <div className="stat-label">skills claimed</div>
              </div>
              <div className="stat">
                <div className="stat-value">
                  {sorted.filter((f) => f.evidence === "none").length}
                </div>
                <div className="stat-label">with no evidence</div>
              </div>
              <div className="stat">
                <div className="stat-value">
                  {sorted.filter((f) => f.evidence === "untracked").length}
                </div>
                <div className="stat-label">Undrift can&rsquo;t see</div>
              </div>
            </div>
          )}

          <ul className="finding-list">
            {sorted.map((f) => (
              <Finding key={`${f.claimed}-${f.skill}`} finding={f} />
            ))}
          </ul>

          <p className="hint" style={{ marginTop: "1.25rem" }}>
            The percentage counts only skills Undrift tracks. Anything it
            can&rsquo;t see is excluded rather than counted against you — a
            blind spot in the tool is not a finding about the person. Evidence
            strength comes from depth (lifetime commits); freshness and staleness
            come from the same decay curve as the dashboard. Claude only maps
            your wording onto the vocabulary; it never decides whether the
            evidence is good.
          </p>
        </>
      )}
    </main>
  );
}

// One skill: the freshness bar, the three axes, the forecast, and -- when you
// click it -- the commits that produced the number.
//
// The card's colour AND its opacity track the score, so a decayed skill looks
// faded next to a fresh one. The whole point of the dashboard should be
// visible before you read a single number.

import { useEffect, useState } from "react";
import { getCommits } from "../api";
import { band } from "../skills";

function Delta({ value }) {
  if (value === null || value === undefined) return null;
  // Below what the label can actually show (one decimal place), call it flat.
  // Consecutive scoring runs minutes apart produce deltas like -0.01, which
  // otherwise rendered as a meaningless "down 0.0".
  if (Math.abs(value) < 0.05) return <span className="delta flat">no change</span>;
  const up = value > 0;
  return (
    <span className={`delta ${up ? "up" : "down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(1)}
    </span>
  );
}

// Momentum is null when there wasn't enough activity to claim a direction --
// see momentum_from_counts in scoring.py. Saying "unknown" is the honest
// render; showing "+100" off a single commit would not be.
function Momentum({ value }) {
  if (value === null || value === undefined) {
    return <span className="axis-value unknown" title="Too few recent commits to call a trend">too few</span>;
  }
  if (Math.abs(value) < 1) return <span className="axis-value">steady</span>;
  const up = value > 0;
  return (
    <span className={`axis-value ${up ? "up" : "down"}`}>
      {up ? "↑" : "↓"} {Math.abs(Math.round(value))}%
    </span>
  );
}

function humanDays(days) {
  if (days === null || days === undefined) return null;
  if (days < 45) return `${Math.round(days)} days`;
  if (days < 365) return `${Math.round(days / 30)} months`;
  return `${(days / 365).toFixed(1)} years`;
}

// What to say about the future, given where the skill sits now. Each band has
// a different useful thing to report, and "already stale" has none at all.
function Forecast({ skill }) {
  const state = band(skill.freshness);

  if (state === "stale") {
    return (
      <div className="forecast">
        <span>Already stale — last used <strong>{Math.round(skill.days_since_last)}d</strong> ago</span>
      </div>
    );
  }

  const target = state === "fresh" ? skill.days_until_fading : skill.days_until_stale;
  const label = state === "fresh" ? "starts fading" : "goes stale";
  const human = humanDays(target);
  if (!human) return null;

  return (
    <div className={`forecast${target < 30 ? " imminent" : ""}`}>
      <span>
        {label} in <strong>{human}</strong> if you don't touch it
      </span>
    </div>
  );
}

// The drawer. Commits are fetched lazily on first open rather than up front:
// there is one request per skill, and most skills are never opened.
function Evidence({ skill, profile }) {
  const [commits, setCommits] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getCommits(profile, skill.skill)
      .then((rows) => !cancelled && setCommits(rows))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [skill.skill, profile]);

  const first = skill.first_commit_at
    ? new Date(skill.first_commit_at).toLocaleDateString(undefined, {
        month: "short",
        year: "numeric",
      })
    : null;

  return (
    <div className="evidence">
      <div className="evidence-summary">
        <span>
          <strong>{skill.commit_count}</strong> commit{skill.commit_count === 1 ? "" : "s"}
        </span>
        {skill.repo_count ? (
          <span>
            across <strong>{skill.repo_count}</strong> repo{skill.repo_count === 1 ? "" : "s"}
          </span>
        ) : null}
        {first && (
          <span>
            first seen <strong>{first}</strong>
          </span>
        )}
        <span>
          last used <strong>{Math.round(skill.days_since_last)}d</strong> ago
        </span>
      </div>

      {error && <p className="error">{error}</p>}
      {!commits && !error && <p className="empty">Loading evidence…</p>}
      {commits && commits.length === 0 && (
        <p className="empty">No individual commits recorded for this skill.</p>
      )}

      {commits && commits.length > 0 && (
        <ul className="commit-list">
          {commits.map((c) => (
            <li className="commit" key={c.sha}>
              <div className="commit-top">
                <span className="commit-sha">{c.sha.slice(0, 7)}</span>
                <span className="commit-repo">{c.repo}</span>
                <span className="commit-msg">{c.message || "(no message)"}</span>
              </div>
              {c.skill_reason && <div className="commit-reason">{c.skill_reason}</div>}
              <div className="commit-conf">
                {c.tag_source === "llm" ? "Claude" : "fallback tagger"}
                {c.skill_confidence != null &&
                  ` · ${Math.round(c.skill_confidence * 100)}% confident`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// The open card is reflected in the URL hash, so a link can point straight at
// one skill's evidence. That is the shareable artefact this whole feature is
// for: "here is why I can claim FastAPI" is a link, not a screenshot.
const hashFor = (name) => `#skill=${encodeURIComponent(name)}`;

function hashMatches(name) {
  if (typeof window === "undefined") return false;
  return window.location.hash === hashFor(name);
}

export default function SkillCard({ skill, profile }) {
  const [open, setOpen] = useState(() => hashMatches(skill.skill));
  // Start the bar at zero so it animates outward on mount. Without this the
  // width is correct on first paint and the transition never runs.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const state = band(skill.freshness);

  return (
    <li className={`skill ${state}${open ? " open" : ""}`}>
      <button
        className="skill-main"
        onClick={() => {
          setOpen((wasOpen) => {
            // Replace rather than push, so opening five cards in a row
            // doesn't bury the back button under five history entries.
            const next = wasOpen ? " " : hashFor(skill.skill);
            window.history.replaceState(null, "", next);
            return !wasOpen;
          });
        }}
        aria-expanded={open}
      >
        <div className="skill-head">
          <span className="skill-name">
            <span className="chevron">▶</span>
            {skill.skill}
          </span>
          <span className="skill-score">{skill.freshness.toFixed(1)}</span>
        </div>

        <div className="bar-track">
          <div
            className="bar-fill"
            style={{ width: mounted ? `${Math.max(skill.freshness, 1)}%` : "0%" }}
          />
        </div>

        <div className="axes">
          <span className="axis">
            <span className="axis-label">Depth</span>
            <span className="axis-value">
              {skill.depth != null ? skill.depth.toFixed(0) : "—"}
            </span>
          </span>
          <span className="axis">
            <span className="axis-label">Momentum</span>
            <Momentum value={skill.momentum} />
          </span>
          <span className="axis">
            <span className="axis-label">Since last</span>
            <span className="axis-value">{Math.round(skill.days_since_last)}d</span>
          </span>
          <span className="axis">
            <span className="axis-label">Change</span>
            <Delta value={skill.delta} />
          </span>
        </div>

        <Forecast skill={skill} />
      </button>

      {open && <Evidence skill={skill} profile={profile} />}
    </li>
  );
}

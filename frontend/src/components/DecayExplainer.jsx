// The decay formula, made playable.
//
// This is the most interesting idea in the project and it was previously only
// described in prose. Drag the half-life and every number below moves, which
// turns "exponential decay with a 60-day half-life" from a sentence you skim
// into something you can feel.
//
// The maths here is a deliberate duplicate of scoring.py -- and that is the
// one place duplication is the right call. Recomputing client-side means the
// slider responds instantly with no request per drag; and because it is a
// pure function of one input, a copy cannot silently disagree with the server
// the way a cached value could. The constants are the API's own, fetched from
// /api/status rather than hardcoded, so a deployment that changes its
// half-life changes this explainer too.

import { useState } from "react";

const HALF_SATURATION = 3.0;

const AGES = [
  { label: "today", days: 0 },
  { label: "2 weeks ago", days: 14 },
  { label: "1 month ago", days: 30 },
  { label: "3 months ago", days: 90 },
  { label: "6 months ago", days: 180 },
  { label: "1 year ago", days: 365 },
];

const weightAt = (ageDays, halfLife) => Math.pow(0.5, ageDays / halfLife);

export default function DecayExplainer({ defaultHalfLife = 60 }) {
  const [halfLife, setHalfLife] = useState(defaultHalfLife);

  // A worked example: ten commits, all made on the same day, seen from
  // increasing distance. Ten is enough to start high so the fade is visible.
  const exampleCommits = 10;
  const scoreAt = (ageDays) => {
    const raw = exampleCommits * weightAt(ageDays, halfLife);
    return (100 * raw) / (raw + HALF_SATURATION);
  };

  return (
    <div className="explainer">
      <div>
        <p className="eyebrow">Step 1 — every commit decays</p>
        <div className="formula">
          weight = 0.5 <b>^</b> (age_in_days / <b>{halfLife}</b>)
        </div>
        <p className="section-sub" style={{ marginTop: "0.9rem" }}>
          The same shape as radioactive half-life. A commit made today counts
          1.0; one made {halfLife} days ago counts 0.5; twice that age, 0.25.
          It approaches zero but never reaches it, so skills fade smoothly
          instead of falling off a cliff on an arbitrary cutoff date.
        </p>

        <div className="slider-row">
          <label htmlFor="halflife">Half-life</label>
          <input
            id="halflife"
            type="range"
            min="14"
            max="180"
            step="1"
            value={halfLife}
            onChange={(e) => setHalfLife(Number(e.target.value))}
          />
          <span className="slider-value">{halfLife}d</span>
        </div>
        <p className="hint">
          Undrift ships with {defaultHalfLife} days — short enough that a skill
          you dropped last quarter visibly fades, long enough that a two-week
          holiday doesn&rsquo;t tank your scores. Drag it and watch the whole
          table move.
        </p>
      </div>

      <div>
        <p className="eyebrow">What that does to a skill</p>
        <p className="section-sub" style={{ marginTop: "0.4rem" }}>
          Ten commits, all made on one day, scored from further and further
          away.
        </p>
        <table className="decay-table">
          <thead>
            <tr>
              <th>Last used</th>
              <th style={{ width: "45%" }}>Freshness</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {AGES.map((age) => {
              const score = scoreAt(age.days);
              return (
                <tr key={age.days}>
                  <td>{age.label}</td>
                  <td>
                    <span
                      className="decay-bar"
                      style={{ width: `${Math.max(score, 1)}%` }}
                    />
                  </td>
                  <td>{score.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="formula" style={{ marginTop: "1rem" }}>
          freshness = 100 × w / (w + <b>3</b>)
        </div>
        <p className="hint">
          Raw weight is unbounded but a bar needs 0&ndash;100. This curve rises
          steeply then flattens, so the gap between &ldquo;never&rdquo; and
          &ldquo;occasionally&rdquo; shows up strongly while the gap between
          &ldquo;a lot&rdquo; and &ldquo;a whole lot&rdquo; barely moves —
          which is right, since past a point more commits don&rsquo;t make you
          sharper.
        </p>
      </div>
    </div>
  );
}

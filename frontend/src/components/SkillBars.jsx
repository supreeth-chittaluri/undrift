// Freshness bars. The bar's colour AND its opacity track the score, so a
// decayed skill literally looks faded next to a fresh one -- the whole point
// of the dashboard is visible before you read a single number.

// Band on the same rounded number the label shows. Comparing the raw value
// against the threshold made 24.98 render as "25.0" in stale red right next
// to a genuine 25.3 in fading amber, which just looks broken.
const shown = (freshness) => Number(freshness.toFixed(1));

function band(freshness) {
  if (freshness >= 60) return "fresh";
  if (freshness >= 25) return "fading";
  return "stale";
}

function Delta({ value }) {
  if (value === null || value === undefined) return null;
  if (Math.abs(value) < 0.01) return <span className="delta flat">no change</span>;
  const up = value > 0;
  return (
    <span className={`delta ${up ? "up" : "down"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(1)}
    </span>
  );
}

export default function SkillBars({ skills }) {
  if (!skills.length) {
    return <p className="empty">No skills scored yet. Run a refresh to pull commits.</p>;
  }

  return (
    <ul className="skill-list">
      {skills.map((s) => (
        <li key={s.skill} className={`skill ${band(shown(s.freshness))}`}>
          <div className="skill-head">
            <span className="skill-name">{s.skill}</span>
            <span className="skill-score">{s.freshness.toFixed(1)}</span>
          </div>

          <div className="bar-track">
            <div
              className="bar-fill"
              style={{
                width: `${Math.max(s.freshness, 1)}%`,
                // Fade the bar itself as the skill decays.
                opacity: 0.35 + (s.freshness / 100) * 0.65,
              }}
            />
          </div>

          <div className="skill-meta">
            <span>{s.commit_count} commit{s.commit_count === 1 ? "" : "s"}</span>
            <span>{Math.round(s.days_since_last)}d since last</span>
            <Delta value={s.delta} />
          </div>
        </li>
      ))}
    </ul>
  );
}

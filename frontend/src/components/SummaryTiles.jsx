// The headline, above the detail: how many skills are in each band, and which
// one is closest to slipping.
//
// A list of twelve bars answers "what are my scores". It does not answer "so
// what should I do", which is the question someone actually opens this with.
// These tiles answer that in one line before the detail starts.

import { band, mostAtRisk } from "../skills";

// What to call the skill with the least runway left. Its distance from the
// edge is the whole story, so the label changes with it: naming a skill
// "at risk" when it has seven months left would cry wolf, and every later
// warning would be worth less.
function riskLabel(risk) {
  if (!risk) return "nothing at risk";
  const days = risk.days_until_stale;
  if (days == null) return "closest to slipping";
  if (days <= 30) return `goes stale in ${Math.round(days)} days`;
  if (days <= 90) return `needs a session within ${Math.round(days / 7)} weeks`;
  return `first to fade — ${Math.round(days / 30)} months out`;
}

export default function SummaryTiles({ skills }) {
  if (!skills.length) return null;

  const counts = { fresh: 0, fading: 0, stale: 0 };
  for (const s of skills) counts[band(s.freshness)] += 1;

  const risk = mostAtRisk(skills);

  return (
    <div className="stats">
      <div className="stat fresh">
        <div className="stat-value">{counts.fresh}</div>
        <div className="stat-label">staying sharp</div>
      </div>
      <div className="stat fading">
        <div className="stat-value">{counts.fading}</div>
        <div className="stat-label">starting to drift</div>
      </div>
      <div className="stat stale">
        <div className="stat-value">{counts.stale}</div>
        <div className="stat-label">gone stale</div>
      </div>
      <div className="stat">
        <div className="stat-value" style={{ fontSize: risk ? "1.05rem" : undefined }}>
          {risk ? risk.skill : "—"}
        </div>
        <div className="stat-label">{riskLabel(risk)}</div>
      </div>
    </div>
  );
}

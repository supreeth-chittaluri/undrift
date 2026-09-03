// The freshness list. One card per skill, sorted by the API (highest first).
//
// `history` is the same array the trend chart below uses. Passing it down
// means the sparklines cost nothing beyond a lookup -- no second request, no
// per-card fetch.

import SkillCard from "./SkillCard";

export default function SkillBars({ skills, profile, history = [] }) {
  if (!skills.length) {
    return <p className="empty">No skills scored yet. Run a refresh to pull commits.</p>;
  }

  const bySkill = new Map(history.map((series) => [series.skill, series.points]));

  return (
    <ul className="skill-list">
      {skills.map((s) => (
        <SkillCard
          key={s.skill}
          skill={s}
          profile={profile}
          history={bySkill.get(s.skill)}
        />
      ))}
    </ul>
  );
}

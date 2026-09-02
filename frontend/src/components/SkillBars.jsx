// The freshness list. One card per skill, sorted by the API (highest first).

import SkillCard from "./SkillCard";

export default function SkillBars({ skills, profile }) {
  if (!skills.length) {
    return <p className="empty">No skills scored yet. Run a refresh to pull commits.</p>;
  }

  return (
    <ul className="skill-list">
      {skills.map((s) => (
        <SkillCard key={s.skill} skill={s} profile={profile} />
      ))}
    </ul>
  );
}

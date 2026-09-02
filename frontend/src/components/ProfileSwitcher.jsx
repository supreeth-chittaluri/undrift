// Picks whose skill profile the dashboard is showing.
//
// Sample profiles are public GitHub accounts seeded as demo data. They carry
// a visible "sample" badge so nobody reads their commit history as the
// owner's own work.

export default function ProfileSwitcher({ profiles, selected, onSelect }) {
  if (profiles.length < 2) return null;

  return (
    <div className="profiles">
      {profiles.map((p) => (
        <button
          key={p.username}
          className={`profile-pill ${p.username === selected ? "active" : ""}`}
          onClick={() => onSelect(p.username)}
        >
          <span className="profile-name">{p.display_name || p.username}</span>
          <span className="profile-count">{p.commit_count}</span>
          {p.is_sample && <span className="sample-badge">sample</span>}
        </button>
      ))}
    </div>
  );
}

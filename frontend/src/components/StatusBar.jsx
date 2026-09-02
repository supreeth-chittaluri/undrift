// The "this is actually automated" strip: what the last run did and when.
// It exists to answer the reasonable suspicion that a portfolio dashboard is
// showing numbers somebody typed in by hand once.

function timeAgo(iso) {
  if (!iso) return "never";
  const mins = Math.floor((Date.now() - new Date(`${iso}Z`).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function StatusBar({ status, onRefresh, refreshing, canRefresh }) {
  if (!status) return null;
  const run = status.last_run;

  return (
    <div className="status-bar">
      <div className="status-items">
        <span><strong>{status.total_commits}</strong> commits</span>
        <span><strong>{status.total_repos}</strong> repos</span>
        <span><strong>{status.distinct_skills}</strong> skills</span>
        <span><strong>{status.llm_tagged_commits}</strong> LLM-tagged</span>
        <span>half-life <strong>{status.half_life_days}d</strong></span>
        <span className={run?.status === "error" ? "run-error" : ""}>
          last sync <strong>{timeAgo(run?.started_at)}</strong>
          {run ? ` (${run.trigger})` : ""}
        </span>
      </div>

      {canRefresh && (
        <button className="ghost" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh now"}
        </button>
      )}
    </div>
  );
}

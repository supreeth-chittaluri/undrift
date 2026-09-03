// A skill's last six months, at thumbnail size.
//
// This costs nothing to add: the trend data is already fetched for the chart
// further down the page, so the same array gets reused here. It earns its
// space because the shape answers a question the number beside it can't --
// 58 on the way up and 58 on the way down are the same score and opposite
// situations.

const W = 68;
const H = 20;

// The y-axis is pinned to 0-100 rather than fitted to this skill's own range.
// A fitted axis would make every sparkline fill its box, so a skill wobbling
// between 71 and 74 would look as dramatic as one falling off a cliff.
const Y_MAX = 100;

export default function Sparkline({ points }) {
  // Two points is the minimum that can describe a direction; anything less is
  // a dot pretending to be a trend.
  if (!points || points.length < 2) return null;

  const values = points.map((p) => p.freshness);
  const step = W / (values.length - 1);
  const y = (v) => H - 1 - (Math.max(0, Math.min(v, Y_MAX)) / Y_MAX) * (H - 2);

  const line = values.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${W},${H} L0,${H} Z`;

  return (
    <svg
      className="spark"
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      aria-hidden="true"
      focusable="false"
    >
      <path className="spark-area" d={area} />
      <path d={line} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

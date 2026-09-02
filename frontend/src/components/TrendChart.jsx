// Freshness over time, one line per skill. Because the backend replays the
// decay formula at past dates, this shows real drift from the first load
// rather than waiting months for snapshots to pile up.

import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler,
);

// Fixed palette so a skill keeps the same colour between renders.
const COLORS = [
  "#4ade80", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa",
  "#22d3ee", "#fb923c", "#f87171", "#94a3b8", "#34d399",
];

export default function TrendChart({ history }) {
  if (!history.length) {
    return <p className="empty">Not enough history yet to draw a trend.</p>;
  }

  // Every series shares one sorted set of dates so the x-axis lines up.
  const labels = [
    ...new Set(history.flatMap((s) => s.points.map((p) => p.date))),
  ].sort();

  const data = {
    labels: labels.map((d) => new Date(d).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
    })),
    datasets: history.map((series, i) => {
      const byDate = new Map(series.points.map((p) => [p.date, p.freshness]));
      return {
        label: series.skill,
        // null gaps break the line where a skill didn't exist yet, which is
        // honest -- we're not pretending it scored zero before its first commit.
        data: labels.map((d) => (byDate.has(d) ? byDate.get(d) : null)),
        borderColor: COLORS[i % COLORS.length],
        backgroundColor: `${COLORS[i % COLORS.length]}22`,
        tension: 0.3,
        spanGaps: false,
        pointRadius: 2,
        borderWidth: 2,
        fill: true,
      };
    }),
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    scales: {
      y: {
        min: 0, max: 100,
        title: { display: true, text: "Freshness", color: "#94a3b8" },
        ticks: { color: "#94a3b8" },
        grid: { color: "#1e293b" },
      },
      x: { ticks: { color: "#94a3b8", maxTicksLimit: 10 }, grid: { display: false } },
    },
    plugins: {
      legend: { labels: { color: "#cbd5e1", boxWidth: 12, usePointStyle: true } },
    },
  };

  return (
    <div className="chart-wrap">
      <Line data={data} options={options} />
    </div>
  );
}

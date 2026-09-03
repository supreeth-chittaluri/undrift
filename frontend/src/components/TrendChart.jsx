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

// Fixed palette so a skill keeps the same colour between renders. These are
// categorical -- they identify a series, they do not encode a value, so they
// deliberately avoid the fresh/fading/stale traffic-light colours that DO
// carry meaning elsewhere in the UI.
const COLORS = [
  "#2f6b3f", "#8a5a2b", "#3b6ea5", "#b07d16", "#7a4a7d",
  "#4a7c6f", "#b0432c", "#5f6d88", "#946c3a", "#2f6b8a",
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
        backgroundColor: `${COLORS[i % COLORS.length]}1a`,
        tension: 0.35,
        spanGaps: false,
        pointRadius: 0,
        pointHoverRadius: 4,
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
        title: { display: true, text: "Freshness", color: "#9a9186" },
        ticks: { color: "#6b6257", font: { size: 11 } },
        grid: { color: "#e6dfd4" },
        border: { display: false },
      },
      x: {
        ticks: { color: "#6b6257", maxTicksLimit: 8, font: { size: 11 } },
        grid: { display: false },
        border: { color: "#e6dfd4" },
      },
    },
    plugins: {
      legend: {
        labels: {
          color: "#6b6257",
          boxWidth: 8,
          usePointStyle: true,
          pointStyle: "circle",
          font: { size: 11 },
          padding: 14,
        },
      },
      tooltip: {
        backgroundColor: "#ffffff",
        borderColor: "#d5cbbc",
        borderWidth: 1,
        titleColor: "#1f1a14",
        bodyColor: "#6b6257",
        padding: 10,
        cornerRadius: 8,
        displayColors: true,
        usePointStyle: true,
      },
    },
  };

  return (
    <div className="chart-wrap">
      <Line data={data} options={options} />
    </div>
  );
}

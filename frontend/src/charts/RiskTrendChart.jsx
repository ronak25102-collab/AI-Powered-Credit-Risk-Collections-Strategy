import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

export default function RiskTrendChart({ rows }) {
  const labels = rows.map((row) => row.label);

  const data = {
    labels,
    datasets: [
      {
        label: "High Risk",
        data: rows.map((row) => row.high),
        borderColor: "#ff7f53",
        backgroundColor: "rgba(255, 127, 83, 0.22)",
        tension: 0.35,
        fill: false,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
      {
        label: "Medium Risk",
        data: rows.map((row) => row.medium),
        borderColor: "#ffb085",
        backgroundColor: "rgba(255, 176, 133, 0.2)",
        tension: 0.35,
        fill: false,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
      {
        label: "Low Risk",
        data: rows.map((row) => row.low),
        borderColor: "#c6916f",
        backgroundColor: "rgba(198, 145, 111, 0.2)",
        tension: 0.35,
        fill: false,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: "index",
      intersect: false,
    },
    scales: {
      x: {
        ticks: { color: "#6b5a50" },
        grid: { color: "rgba(237, 220, 207, 0.72)" },
      },
      y: {
        ticks: { color: "#6b5a50" },
        grid: { color: "rgba(237, 220, 207, 0.72)" },
      },
    },
    plugins: {
      legend: {
        labels: { color: "#5e4b40" },
      },
    },
  };

  return (
    <div className="h-[300px]">
      <Line data={data} options={options} />
    </div>
  );
}

import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export default function FeatureCorrelationChart({ correlations }) {
  const entries = Object.entries(correlations || {});
  const labels = entries.map(([feature]) => feature.replaceAll("_", " "));

  const data = {
    labels,
    datasets: [
      {
        label: "Correlation with Delinquency",
        data: entries.map(([, value]) => value),
        backgroundColor: entries.map(([, value]) =>
          value >= 0 ? "rgba(255, 139, 84, 0.88)" : "rgba(232, 177, 147, 0.84)"
        ),
        borderRadius: 8,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        ticks: { color: "#6f4f41", maxRotation: 35, minRotation: 35 },
        grid: { color: "rgba(255, 173, 130, 0.26)" },
      },
      y: {
        ticks: { color: "#6f4f41" },
        grid: { color: "rgba(255, 173, 130, 0.26)" },
      },
    },
    plugins: {
      legend: {
        labels: { color: "#6c4c3f" },
      },
    },
  };

  return (
    <div className="h-[310px]">
      <Bar data={data} options={options} />
    </div>
  );
}

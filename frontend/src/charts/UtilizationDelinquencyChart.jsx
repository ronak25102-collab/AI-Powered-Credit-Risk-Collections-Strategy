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

export default function UtilizationDelinquencyChart({ rows }) {
  const labels = rows.map((row) => row.bucket);

  const data = {
    labels,
    datasets: [
      {
        label: "Non Delinquent",
        data: rows.map((row) => row.non_delinquent),
        backgroundColor: "rgba(255, 214, 188, 0.88)",
      },
      {
        label: "Delinquent",
        data: rows.map((row) => row.delinquent),
        backgroundColor: "rgba(255, 127, 98, 0.86)",
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        stacked: true,
        ticks: { color: "#6f4f41" },
        grid: { color: "rgba(255, 173, 130, 0.26)" },
      },
      y: {
        stacked: true,
        ticks: { color: "#6f4f41" },
        grid: { color: "rgba(255, 173, 130, 0.26)" },
      },
    },
    plugins: {
      legend: {
        labels: { color: "#6c4c3f" },
      },
      tooltip: {
        mode: "index",
        intersect: false,
      },
    },
  };

  return (
    <div className="h-[260px]">
      <Bar data={data} options={options} />
    </div>
  );
}

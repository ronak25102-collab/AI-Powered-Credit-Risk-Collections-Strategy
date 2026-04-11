import {
  ArcElement,
  Chart as ChartJS,
  Legend,
  Tooltip,
} from "chart.js";
import { Pie } from "react-chartjs-2";

ChartJS.register(ArcElement, Tooltip, Legend);

export default function RiskDistributionChart({ distribution }) {
  const data = {
    labels: ["Low", "Medium", "High"],
    datasets: [
      {
        data: [distribution.low, distribution.medium, distribution.high],
        backgroundColor: ["#ffd5b7", "#ffad7c", "#ff7f62"],
        borderColor: ["rgba(255,255,255,0.7)", "rgba(255,255,255,0.7)", "rgba(255,255,255,0.7)"],
        borderWidth: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: {
          color: "#6c4c3f",
          padding: 16,
        },
      },
      tooltip: {
        callbacks: {
          label: (context) => `${context.label}: ${context.raw}`,
        },
      },
    },
  };

  return (
    <div className="h-[260px]">
      <Pie data={data} options={options} />
    </div>
  );
}

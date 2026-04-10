import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler
);

function EcgChart({ points }) {
  const labels = points.map((_, i) => i + 1);

  const data = {
    labels,
    datasets: [
      {
        label: 'ECG Signal',
        data: points,
        borderColor: '#14b8a6',
        backgroundColor: 'rgba(20, 184, 166, 0.18)',
        borderWidth: 2.5,
        pointRadius: 0,
        fill: true,
        tension: 0.5
      }
    ]
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        labels: {
          color: '#e2e8f0'
        }
      }
    },
    scales: {
      x: {
        ticks: { display: false },
        grid: { color: 'rgba(148, 163, 184, 0.15)' }
      },
      y: {
        min: 1000,
        max: 3000,
        ticks: { color: '#cbd5e1' },
        grid: { color: 'rgba(148, 163, 184, 0.15)' }
      }
    }
  };

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h2>Live ECG</h2>
      </div>
      <div className="chart-wrap">
        <Line className="w-full h-full" data={data} options={options} />
      </div>
    </section>
  );
}

export default EcgChart;

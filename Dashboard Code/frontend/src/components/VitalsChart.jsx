import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

function VitalsChart({ pulsePoints, spo2Points }) {
  const size = Math.max(pulsePoints.length, spo2Points.length);
  const labels = Array.from({ length: size }, (_, i) => i + 1);

  const data = {
    labels,
    datasets: [
      {
        label: 'Pulse (BPM)',
        data: pulsePoints,
        borderColor: '#f97316',
        backgroundColor: 'rgba(249, 115, 22, 0.18)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.22,
        yAxisID: 'pulse'
      },
      {
        label: 'SpO2 (%)',
        data: spo2Points,
        borderColor: '#22c55e',
        backgroundColor: 'rgba(34, 197, 94, 0.16)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.2,
        yAxisID: 'spo2'
      }
    ]
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {
      mode: 'index',
      intersect: false
    },
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
      pulse: {
        type: 'linear',
        position: 'left',
        min: 40,
        max: 160,
        ticks: { color: '#fdba74' },
        grid: { color: 'rgba(148, 163, 184, 0.15)' }
      },
      spo2: {
        type: 'linear',
        position: 'right',
        min: 80,
        max: 100,
        ticks: { color: '#86efac' },
        grid: { drawOnChartArea: false }
      }
    }
  };

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h2>Pulse & Oximeter Trend</h2>
      </div>
      <div className="chart-wrap vitals-chart-wrap">
        <Line data={data} options={options} />
      </div>
    </section>
  );
}

export default VitalsChart;

import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip
} from 'chart.js';
import { useMemo, useState } from 'react';
import { Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

function OximeterChart({ points }) {
  const [windowSize, setWindowSize] = useState(120);
  const [yMin, setYMin] = useState(80);
  const [yMax, setYMax] = useState(100);

  const safeWindow = Math.max(20, Math.min(300, windowSize || 120));
  const trimmedPoints = useMemo(() => points.slice(-safeWindow), [points, safeWindow]);
  const labels = trimmedPoints.map((_, i) => i + 1);

  const data = {
    labels,
    datasets: [
      {
        label: 'SpO2 (%)',
        data: trimmedPoints,
        borderColor: '#22c55e',
        backgroundColor: 'rgba(34, 197, 94, 0.16)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.22
      }
    ]
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        labels: { color: '#e2e8f0' }
      }
    },
    scales: {
      x: {
        ticks: { display: false },
        grid: { color: 'rgba(148, 163, 184, 0.15)' }
      },
      y: {
        min: Math.min(yMin, yMax - 1),
        max: Math.max(yMax, yMin + 1),
        ticks: { color: '#86efac' },
        grid: { color: 'rgba(148, 163, 184, 0.15)' }
      }
    }
  };

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h2>Oximeter Analytics</h2>
      </div>
      <div className="chart-controls">
        <label>
          Window
          <input
            type="number"
            min="20"
            max="300"
            value={windowSize}
            onChange={(e) => setWindowSize(Number(e.target.value))}
          />
        </label>
        <label>
          Y Min
          <input
            type="number"
            min="60"
            max="100"
            value={yMin}
            onChange={(e) => setYMin(Number(e.target.value))}
          />
        </label>
        <label>
          Y Max
          <input
            type="number"
            min="80"
            max="100"
            value={yMax}
            onChange={(e) => setYMax(Number(e.target.value))}
          />
        </label>
      </div>
      <div className="chart-wrap mini-chart-wrap">
        <Line className="w-full h-full" data={data} options={options} />
      </div>
    </section>
  );
}

export default OximeterChart;

function Metrics({ pulse, spo2, stress, connected, healthStatus, confidence }) {
  const stressClass = stress ? 'danger' : 'safe';
  const healthClass = `health-${healthStatus || 'healthy'}`;

  function getHealthLabel(status) {
    if (status === 'stressed') return 'Stressed';
    if (status === 'depressed') return 'Depressed Pattern';
    return 'Healthy';
  }

  return (
    <section className="metrics-grid">
      <article className="panel metric-card">
        <h3>Pulse</h3>
        <p className="metric-value">{Math.round(pulse || 0)} BPM</p>
      </article>

      <article className="panel metric-card metric-spo2">
        <h3>Oximeter (SpO2)</h3>
        <p className="metric-value">{(spo2 || 0).toFixed(1)}%</p>
      </article>

      <article className={`panel metric-card ${stressClass}`}>
        <h3>Stress Status</h3>
        <p className="metric-value">{stress ? 'Detected' : 'Normal'}</p>
      </article>

      <article className={`panel metric-card ${healthClass}`}>
        <h3>Health Status</h3>
        <p className="metric-value">{getHealthLabel(healthStatus)}</p>
      </article>

      <article className="panel metric-card">
        <h3>Prediction Confidence</h3>
        <p className="metric-value">{Math.round((confidence || 0) * 100)}%</p>
      </article>

      <article className={`panel metric-card ${connected ? 'online' : 'offline'}`}>
        <h3>Connection</h3>
        <p className="metric-value">{connected ? 'Online' : 'Offline / Mock'}</p>
      </article>
    </section>
  );
}

export default Metrics;

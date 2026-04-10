function Metrics({ pulse, spo2, stress, connected, healthStatus, confidence }) {
  const stressClass = stress === "Stress" ? 'danger' : 'safe';
  const healthClass = `health-${healthStatus || 'healthy'}`;

  function getHealthLabel(status) {
    if (status === 'warning') return 'Warning';
    if (status === 'calibrating') return 'Calibrating...';
    if (status === 'stressed') return 'Stressed';
    if (status === 'depressed') return 'Depressed Pattern';
    return 'Healthy';
  }

  // 🔥 NEW: Using inline styles to guarantee it overrides any custom CSS files
  const highlightStyle = stress === "Stress" 
    ? { border: "3px solid #ef4444", boxShadow: "0 0 15px rgba(239,68,68,0.4)", transition: "all 0.5s" }
    : stress === "No Stress"
    ? { border: "3px solid #22c55e", boxShadow: "0 0 15px rgba(34,197,94,0.4)", transition: "all 0.5s" }
    : { border: "3px solid transparent", transition: "all 0.5s" };

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

      {/* 🔴 APPLIED INLINE STYLE HERE */}
      <article className={`panel metric-card ${stressClass}`} style={highlightStyle}>
        <h3>Stress Status</h3>
        <p className="metric-value">{stress === null ? 'Waiting...' : stress}</p>
      </article>

      {/* 🔴 APPLIED INLINE STYLE HERE */}
      <article className={`panel metric-card ${healthClass}`} style={highlightStyle}>
        <h3>Health Status</h3>
        <p className="metric-value">{getHealthLabel(healthStatus)}</p>
      </article>

      {/* 🔴 APPLIED INLINE STYLE HERE */}
      <article className="panel metric-card" style={highlightStyle}>
        <h3>Prediction Confidence</h3>
        <p className="metric-value">{stress === null ? '--' : `${Math.round((confidence || 0) * 100)}%`}</p>
      </article>

      <article className={`panel metric-card ${connected ? 'online' : 'offline'}`}>
        <h3>Connection</h3>
        <p className="metric-value">{connected ? 'Online' : 'Offline'}</p>
      </article>
    </section>
  );
}

export default Metrics;
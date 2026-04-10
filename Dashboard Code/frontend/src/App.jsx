import { useEffect, useMemo, useState } from 'react';
import EcgChart from './components/EcgChart';
import Metrics from './components/Metrics';
import OximeterChart from './components/OximeterChart';
import PulseChart from './components/PulseChart';

const MAX_POINTS = 200;
const MAX_VITAL_POINTS = 160;
const MAX_ECG_POINTS = 300;

function App() {
  const [ecgPoints, setEcgPoints] = useState([]);
  const [bpm, setBpm] = useState(0);
  const [spo2, setSpo2] = useState(0);
  const [pulsePoints, setPulsePoints] = useState([]);
  const [spo2Points, setSpo2Points] = useState([]);
  
  // Model & Buffer States
  const [stress, setStress] = useState(null);
  const [healthStatus, setHealthStatus] = useState('healthy');
  const [confidence, setConfidence] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [required, setRequired] = useState(12000);
  
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      fetch("http://10.14.92.61:5000/data")
        .then((res) => res.json())
        .then((payload) => {

          // BPM
          if (payload.bpm > 0) {
            setBpm(payload.bpm);
            setPulsePoints((prev) => {
              const next = [...prev, payload.bpm];
              if (next.length > MAX_VITAL_POINTS) next.shift();
              return next;
            });
          }

          // SpO2
          if (payload.spo2 > 0) {
            setSpo2(payload.spo2);
            setSpo2Points((prev) => {
              const next = [...prev, payload.spo2];
              if (next.length > MAX_VITAL_POINTS) next.shift();
              return next;
            });
          }

          // ECG
          if (typeof payload.ecg === "number") {
            setEcgPoints((prev) => {
              const next = [...prev, payload.ecg];
              if (next.length > MAX_ECG_POINTS) next.shift();
              return next;
            });
          }

          // 🔥 NEW: Update Model Predictions
          setBuffered(payload.buffered || 0);
          setRequired(payload.required || 12000);
          
          if (payload.stress !== null) {
            setStress(payload.stress);
            setConfidence(payload.confidence);
            // Automatically change health status based on stress
            setHealthStatus(payload.stress === "Stress" ? "warning" : "healthy");
          } else {
            // Reset to null if buffer clears or disconnected
            setStress(null);
            setConfidence(null);
            setHealthStatus('calibrating');
          }

          setConnected(true);
        })
        .catch(() => setConnected(false));

    }, 50); // Polling every 50ms

    return () => clearInterval(interval);
  }, []);

  const pageStatus = useMemo(() => {
    return connected ? 'Hardware Connected' : 'Waiting for Device';
  }, [connected]);

  // 🔥 NEW: Calculate seconds remaining (200 samples = 1 sec)
  const secondsRemaining = Math.max(0, Math.ceil((required - buffered) / 200));

return (
    <main className="min-h-screen w-full overflow-x-hidden p-3 md:p-4">
      <section className="mx-auto flex w-full max-w-[1800px] flex-col gap-4 md:flex-row">

        {/* -------- SIDEBAR -------- */}
        <aside className="flex w-full flex-col gap-4 md:w-72">
          <section className="panel side-panel">
            <h1>Stress IoT</h1>
            <p className="subtitle">Real-time physiological monitoring dashboard</p>
            <div className={`status-pill ${connected ? 'online' : 'offline'}`}>
              {pageStatus}
            </div>
          </section>

          {/* 🔥 NEW: Dynamic Border Highlight around the Metrics panel */}
          <aside className="flex w-full flex-col gap-4 md:w-72">
            <Metrics
              pulse={bpm}
              spo2={spo2}
              stress={stress}
              connected={connected}
              healthStatus={healthStatus}
              confidence={confidence}
            />
          </aside>
        </aside>

        {/* -------- MAIN -------- */}
        <section className="flex flex-1 flex-col gap-4">

          <div className="mb-4 flex w-full justify-center">
              <div className="rounded-full bg-gray-100 px-4 py-2 font-mono text-sm shadow-sm dark:bg-gray-800">
                {secondsRemaining > 0 
                  ? `⏳ Gathering baseline: ${secondsRemaining}s remaining` 
                  : `✅ Model Active (Buffer: ${buffered}/${required})`}
              </div>
            </div>
          {/* 🔴 ECG Section */}
          <section className="panel opacity-100">
            
            {/* Centered Buffer Countdown Display */}
            

            <EcgChart points={ecgPoints} />
          </section>

          {/* -------- CHARTS -------- */}
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <PulseChart points={pulsePoints} />
            <OximeterChart points={spo2Points} />
          </section>

        </section>
      </section>
    </main>
  );
}
export default App;
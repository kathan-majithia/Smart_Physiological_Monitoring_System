import { useEffect, useMemo, useState } from 'react';
import EcgChart from './components/EcgChart';
import Metrics from './components/Metrics';
import OximeterChart from './components/OximeterChart';
import PulseChart from './components/PulseChart';

const MAX_POINTS = 200;
const MAX_VITAL_POINTS = 160;

function App() {
  const [ecgPoints, setEcgPoints] = useState([]);
  const [bpm, setBpm] = useState(0);
  const [spo2, setSpo2] = useState(0);
  const [pulsePoints, setPulsePoints] = useState([]);
  const [spo2Points, setSpo2Points] = useState([]);
  const [stress, setStress] = useState(false);
  const [healthStatus, setHealthStatus] = useState('healthy');
  const [confidence, setConfidence] = useState(0);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
  const interval = setInterval(() => {
    fetch("http://10.14.92.61:5000/data")
      .then((res) => res.json())
      .then((payload) => {
        console.log("DATA:", payload);

        // -------- BPM --------
        if (typeof payload?.bpm === "number" && payload.bpm > 0) {
          setBpm(payload.bpm);

          setPulsePoints((prev) => {
            const next = [...prev, payload.bpm];
            if (next.length > MAX_VITAL_POINTS) next.shift();
            return next;
          });
        }

        console.log("Pulsepoint : ",pulsePoints.length)

        // -------- SpO2 --------
        if (typeof payload?.spo2 === "number" && payload.spo2 > 0) {
          setSpo2(payload.spo2);

          setSpo2Points((prev) => {
            const next = [...prev, payload.spo2];
            if (next.length > MAX_VITAL_POINTS) next.shift();
            return next;
          });
        }

        setConnected(true);
      })
      .catch((err) => {
        console.log("ERROR:", err);
        setConnected(false);
      });
  }, 1000);

  return () => clearInterval(interval);
}, []);

  const pageStatus = useMemo(() => {
    return connected ? 'Hardware Connected' : 'Waiting for Device';
  }, [connected]);

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

          <Metrics
            pulse={bpm}
            spo2={spo2}
            stress={stress}
            connected={connected}
            healthStatus={healthStatus}
            confidence={confidence}
          />
        </aside>

        {/* -------- MAIN -------- */}
        <section className="flex flex-1 flex-col gap-4">

          {/* 🔴 ECG DISABLED (no sensor yet) */}
          <section className="panel opacity-40">
            <h2>ECG (Disabled - No Sensor)</h2>
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
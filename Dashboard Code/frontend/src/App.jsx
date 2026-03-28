import { useEffect, useMemo, useState } from 'react';
import EcgChart from './components/EcgChart';
import Metrics from './components/Metrics';
import OximeterChart from './components/OximeterChart';
import PulseChart from './components/PulseChart';
import { socket } from './socket';

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
    function onConnect() {
      setConnected(true);
    }

    function onDisconnect() {
      setConnected(false);
    }

    function onTelemetry(payload) {
      if (typeof payload?.ecg === 'number') {
        setEcgPoints((prev) => {
          const next = [...prev, payload.ecg];
          if (next.length > MAX_POINTS) {
            next.shift();
          }
          return next;
        });
      }

      if (typeof payload?.bpm === 'number') {
        setBpm(payload.bpm);
      }

      if (typeof payload?.pulse === 'number') {
        setBpm(payload.pulse);
        setPulsePoints((prev) => {
          const next = [...prev, payload.pulse];
          if (next.length > MAX_VITAL_POINTS) {
            next.shift();
          }
          return next;
        });
      }

      if (typeof payload?.spo2 === 'number') {
        setSpo2(payload.spo2);
        setSpo2Points((prev) => {
          const next = [...prev, payload.spo2];
          if (next.length > MAX_VITAL_POINTS) {
            next.shift();
          }
          return next;
        });
      }

      if (typeof payload?.stress === 'boolean') {
        setStress(payload.stress);
      }

      if (typeof payload?.health_status === 'string') {
        setHealthStatus(payload.health_status);
      }

      if (typeof payload?.confidence === 'number') {
        setConfidence(payload.confidence);
      }

      if (typeof payload?.connected === 'boolean') {
        setConnected(payload.connected);
      }
    }

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('telemetry', onTelemetry);

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('telemetry', onTelemetry);
    };
  }, []);

  const pageStatus = useMemo(() => {
    return connected ? 'Hardware Connected' : 'Waiting for Device / Mock Stream';
  }, [connected]);

  return (
    <main className="min-h-screen w-full overflow-x-hidden p-3 md:p-4">
      <section className="mx-auto flex w-full max-w-[1800px] flex-col items-stretch gap-4 md:flex-row">
        <aside className="flex w-full flex-col gap-4 md:w-72 md:min-w-72 md:max-w-72 md:flex-shrink-0">
          <section className="panel side-panel w-full max-w-full overflow-hidden">
            <h1>Stress IoT</h1>
            <p className="subtitle">Real-time physiological monitoring dashboard</p>
            <div className={`status-pill ${connected ? 'online' : 'offline'}`}>
              {pageStatus}
            </div>
          </section>

          <section className="w-full max-w-full overflow-hidden">
            <Metrics
              pulse={bpm}
              spo2={spo2}
              stress={stress}
              connected={connected}
              healthStatus={healthStatus}
              confidence={confidence}
            />
          </section>
        </aside>

        <section className="flex min-w-0 max-w-full flex-1 flex-col gap-4 overflow-hidden min-h-0">
          <section className="w-full min-w-0 max-w-full overflow-hidden min-h-0">
            <EcgChart points={ecgPoints} />
          </section>

          <section className="grid min-w-0 max-w-full grid-cols-1 gap-4 md:grid-cols-2 min-h-0">
            <section className="w-full min-w-0 max-w-full overflow-hidden min-h-0">
              <PulseChart points={pulsePoints} />
            </section>
            <section className="w-full min-w-0 max-w-full overflow-hidden min-h-0">
              <OximeterChart points={spo2Points} />
            </section>
          </section>
        </section>
      </section>
    </main>
  );
}

export default App;

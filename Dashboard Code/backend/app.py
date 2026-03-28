import math
import os
import pickle
import random
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

try:
    import serial
except ImportError:
    serial = None


SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
EMIT_HZ = float(os.getenv("EMIT_HZ", "50"))
MAX_BUFFER = int(os.getenv("MAX_BUFFER", "256"))

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

sample_buffer = deque(maxlen=MAX_BUFFER)
ml_model = None
serial_connected = False


@app.get("/")
def health():
    return jsonify({"status": "ok", "service": "stress-iot-backend"})


@app.get("/api/status")
def status():
    return jsonify(
        {
            "serial_port": SERIAL_PORT,
            "baud_rate": BAUD_RATE,
            "emit_hz": EMIT_HZ,
            "serial_connected": serial_connected,
            "buffer_size": len(sample_buffer),
            "model_loaded": ml_model is not None,
        }
    )


def load_model() -> object | None:
    model_path = Path(__file__).with_name("model.pkl")
    if not model_path.exists():
        return None

    try:
        with model_path.open("rb") as f:
            return pickle.load(f)
    except Exception:
        # If model file is a placeholder or invalid, continue with fallback rule.
        return None


def parse_csv_line(line: str) -> dict | None:
    parts = line.strip().split(",")
    if len(parts) != 4:
        return None

    try:
        ecg = float(parts[0])
        ir = float(parts[1])
        red = float(parts[2])
        bpm = float(parts[3])
        return {"ecg": ecg, "ir": ir, "red": red, "bpm": bpm}
    except ValueError:
        return None


def make_features() -> list[float]:
    if not sample_buffer:
        return [0.0, 0.0, 0.0]

    ecg_values = [row["ecg"] for row in sample_buffer]
    bpm_values = [row["bpm"] for row in sample_buffer]

    avg_ecg = sum(ecg_values) / len(ecg_values)
    avg_bpm = sum(bpm_values) / len(bpm_values)
    variability = max(bpm_values) - min(bpm_values)
    return [avg_ecg, avg_bpm, variability]


def estimate_spo2() -> float:
    if not sample_buffer:
        return 0.0

    # Use a short rolling window to stabilize the optical ratio.
    recent = list(sample_buffer)[-30:]
    ratios = []
    for row in recent:
        ir = row.get("ir", 0.0)
        red = row.get("red", 0.0)
        if ir > 0 and red > 0:
            ratios.append(red / ir)

    if not ratios:
        return 0.0

    ratio = sum(ratios) / len(ratios)
    spo2 = 110.0 - (25.0 * ratio)
    return round(max(70.0, min(100.0, spo2)), 1)


def predict_health_status() -> dict:
    features = make_features()
    avg_bpm = features[1]
    variability = features[2]

    # Default score profile from rule-based fallback.
    stress_score = 0.1
    depressed_score = 0.1
    healthy_score = 0.8

    if avg_bpm > 100 and variability < 6:
        stress_score = 0.82
        depressed_score = 0.08
        healthy_score = 0.10
    elif avg_bpm < 62 and variability < 5:
        depressed_score = 0.78
        stress_score = 0.10
        healthy_score = 0.12
    elif 62 <= avg_bpm <= 95 and variability >= 6:
        healthy_score = 0.82
        stress_score = 0.10
        depressed_score = 0.08

    if ml_model is not None:
        try:
            pred = ml_model.predict([features])[0]

            # Preferred model labels: healthy/stressed/depressed.
            if isinstance(pred, str):
                pred_label = pred.strip().lower()
                if pred_label in {"healthy", "stressed", "depressed"}:
                    if pred_label == "healthy":
                        healthy_score, stress_score, depressed_score = 0.9, 0.05, 0.05
                    elif pred_label == "stressed":
                        healthy_score, stress_score, depressed_score = 0.05, 0.9, 0.05
                    else:
                        healthy_score, stress_score, depressed_score = 0.05, 0.05, 0.9

            # Compatibility: binary models that output 0/1 stress prediction.
            elif isinstance(pred, (int, bool)):
                if bool(pred):
                    healthy_score, stress_score, depressed_score = 0.08, 0.84, 0.08
                else:
                    healthy_score, stress_score, depressed_score = 0.84, 0.08, 0.08

            # Use probabilistic output when available.
            if hasattr(ml_model, "predict_proba"):
                proba = ml_model.predict_proba([features])[0]
                classes = [str(c).strip().lower() for c in getattr(ml_model, "classes_", [])]
                if len(classes) == len(proba):
                    by_label = dict(zip(classes, proba))
                    if {"healthy", "stressed", "depressed"}.issubset(by_label.keys()):
                        healthy_score = float(by_label["healthy"])
                        stress_score = float(by_label["stressed"])
                        depressed_score = float(by_label["depressed"])
                    elif {"0", "1"}.issubset(by_label.keys()):
                        stress_score = float(by_label["1"])
                        healthy_score = 1.0 - stress_score
                        depressed_score = 0.0
        except Exception:
            pass

    scores = {
        "healthy": healthy_score,
        "stressed": stress_score,
        "depressed": depressed_score,
    }
    health_status = max(scores, key=scores.get)
    confidence = float(scores[health_status])

    return {
        "health_status": health_status,
        "stress": health_status == "stressed",
        "confidence": round(confidence, 3),
        "scores": {k: round(float(v), 3) for k, v in scores.items()},
    }


def emit_payload(row: dict, source_connected: bool) -> None:
    global serial_connected
    serial_connected = source_connected

    sample_buffer.append(row)

    prediction = predict_health_status()
    spo2 = estimate_spo2()

    payload = {
        "ecg": row["ecg"],
        "bpm": row["bpm"],
        "pulse": row["bpm"],
        "spo2": spo2,
        "stress": prediction["stress"],
        "health_status": prediction["health_status"],
        "confidence": prediction["confidence"],
        "scores": prediction["scores"],
        "connected": source_connected,
        "timestamp": time.time(),
    }
    socketio.emit("telemetry", payload)


def generate_mock_row(tick: int) -> dict:
    baseline = 1.2 * math.sin(tick / 7) + 0.2 * math.sin(tick / 2)
    noise = random.uniform(-0.08, 0.08)
    ecg = baseline + noise
    bpm = random.uniform(72, 98)
    ir = random.uniform(48000, 62000)
    red = ir * random.uniform(0.45, 0.62)
    return {"ecg": ecg, "ir": ir, "red": red, "bpm": bpm}


def serial_reader() -> None:
    if serial is None:
        print("pyserial not available. Starting in mock mode.")
        run_mock_stream()
        return

    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                print(f"Serial connected on {SERIAL_PORT} @ {BAUD_RATE}")
                while True:
                    raw = ser.readline().decode("utf-8", errors="ignore").strip()
                    if not raw:
                        continue

                    row = parse_csv_line(raw)
                    if row is None:
                        continue

                    emit_payload(row, source_connected=True)
                    socketio.sleep(1 / EMIT_HZ)
        except Exception as exc:
            print(f"Serial disconnected or unavailable ({exc}). Switching to mock mode.")
            run_mock_stream(duration_seconds=5)


def run_mock_stream(duration_seconds: int | None = None) -> None:
    tick = 0
    started = time.time()

    while True:
        row = generate_mock_row(tick)
        emit_payload(row, source_connected=False)

        tick += 1
        socketio.sleep(1 / EMIT_HZ)

        if duration_seconds is not None and (time.time() - started) >= duration_seconds:
            return


def start_background_reader() -> None:
    thread = threading.Thread(target=serial_reader, daemon=True)
    thread.start()


if __name__ == "__main__":
    ml_model = load_model()
    start_background_reader()
    socketio.run(app, host="0.0.0.0", port=5000)

from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np
import joblib
import threading
from collections import deque
from scipy import signal

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
ECG_SAMPLE_RATE  = 200                             # Hz (1 sample every 5ms)
WINDOW_SECONDS   = 60                              # seconds per prediction window
WINDOW_SAMPLES   = ECG_SAMPLE_RATE * WINDOW_SECONDS  # 12000 samples

MODEL_PATH    = "model_output/stress_model.pkl"
SCALER_PATH   = "model_output/scaler.pkl"

# Exact feature order the model was trained on
FEATURE_NAMES = [
    'mean_rr', 'sdnn', 'rmssd', 'nn50', 'pnn50', 'mean_hr', 
    'sdsd', 'cv_rr', 'vlf_power', 'lf_power', 'hf_power', 
    'total_power', 'lf_hf_ratio', 'lf_norm', 'hf_norm', 'sd1', 'sd2', 
    'sd1_sd2_ratio', 'spo2'
]

# ─────────────────────────────────────────────────────────────────────────────
# LOAD MODEL
# ─────────────────────────────────────────────────────────────────────────────
model  = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)
print(f"✅ Model loaded successfully")

# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE
# ─────────────────────────────────────────────────────────────────────────────
lock        = threading.Lock()
ecg_buffer  = deque(maxlen=WINDOW_SAMPLES)
spo2_buffer = deque(maxlen=WINDOW_SECONDS) # 🔥 NEW: Holds the last 60 SpO2 readings

latest_data = {
    "bpm":        0,
    "spo2":       0,        # This will still show the latest instantaneous value
    "ecg":        0,
    "stress":     None,     # "Stress" | "No Stress" | None
    "confidence": None,     # 0.0 – 1.0
    "buffered":   0,
    "required":   WINDOW_SAMPLES,
}

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL PROCESSING (inlined from training script)
# ─────────────────────────────────────────────────────────────────────────────
def bandpass_filter(ecg_signal, lowcut=0.5, highcut=40.0, fs=200, order=4):
    nyq  = 0.5 * fs
    low  = lowcut / nyq
    high = highcut / nyq
    b, a = signal.butter(order, [low, high], btype='band')
    return signal.filtfilt(b, a, ecg_signal)


def detect_r_peaks(ecg_signal, fs=200):
    diff_ecg   = np.diff(ecg_signal)
    squared    = diff_ecg ** 2
    window_size = int(0.15 * fs)
    integrated = np.convolve(squared, np.ones(window_size) / window_size, mode='same')

    min_distance = int(0.2 * fs)
    threshold    = np.mean(integrated) + 0.5 * np.std(integrated)

    peaks = []
    i = 0
    while i < len(integrated):
        if integrated[i] > threshold:
            start = i
            while i < len(integrated) and integrated[i] > threshold:
                i += 1
            end      = i
            peak_idx = start + np.argmax(integrated[start:end])
            if not peaks or (peak_idx - peaks[-1]) >= min_distance:
                peaks.append(peak_idx)
        i += 1
    return np.array(peaks)


def compute_hrv_features(rr_intervals_ms, spo2=98.0):
    """Compute all 19 features the model expects."""
    if len(rr_intervals_ms) < 4:
        return None

    rr = np.array(rr_intervals_ms, dtype=float)

    # ── Time domain ──────────────────────────────────────────────────────
    mean_rr = np.mean(rr)
    sdnn    = np.std(rr)
    rmssd   = np.sqrt(np.mean(np.diff(rr) ** 2))
    nn50    = int(np.sum(np.abs(np.diff(rr)) > 50))
    pnn50   = (nn50 / len(rr)) * 100
    mean_hr = 60000.0 / mean_rr
    sdsd    = np.std(np.diff(rr))
    cv_rr   = (sdnn / mean_rr) * 100

    # ── Frequency domain (Welch PSD) ─────────────────────────────────────
    try:
        rr_times  = np.cumsum(rr) / 1000.0
        interp_fs = 4.0
        t_interp  = np.arange(rr_times[0], rr_times[-1], 1.0 / interp_fs)
        rr_interp = np.interp(t_interp, rr_times, rr)

        freqs, psd = signal.welch(rr_interp, fs=interp_fs,
                                  nperseg=min(len(rr_interp), 256))

        def band_power(freqs, psd, low, high):
            idx = np.where((freqs >= low) & (freqs < high))[0]
            return float(np.trapz(psd[idx], freqs[idx])) if len(idx) > 0 else 0.0

        vlf_power   = band_power(freqs, psd, 0.003, 0.04)
        lf_power    = band_power(freqs, psd, 0.04,  0.15)
        hf_power    = band_power(freqs, psd, 0.15,  0.40)
        total_power = vlf_power + lf_power + hf_power

        lf_hf_ratio = lf_power / (hf_power + 1e-10)
        lf_norm     = lf_power / (lf_power + hf_power + 1e-10) * 100
        hf_norm     = hf_power / (lf_power + hf_power + 1e-10) * 100

    except Exception:
        vlf_power = lf_power = hf_power = total_power = 0.0
        lf_hf_ratio = lf_norm = hf_norm = 0.0

    # ── Non-linear (Poincaré) ─────────────────────────────────────────────
    sd1          = np.sqrt(0.5) * np.std(np.diff(rr))
    sd2          = np.sqrt(max(2 * sdnn**2 - 0.5 * np.std(np.diff(rr))**2, 0))
    sd1_sd2_ratio = sd1 / (sd2 + 1e-10)

    # ── Return in exact FEATURE_NAMES order ───────────────────────────────
    return {
        "mean_rr":       mean_rr,
        "mean_hr":       mean_hr,
        "cv_rr":         cv_rr,
        "nn50":          nn50,
        "hf_power":      hf_power,
        "pnn50":         pnn50,
        "sd2":           sd2,
        "vlf_power":     vlf_power,
        "total_power":   total_power,
        "sdnn":          sdnn,
        "sdsd":          sdsd,
        "sd1":           sd1,
        "lf_power":      lf_power,
        "rmssd":         rmssd,
        "sd1_sd2_ratio": sd1_sd2_ratio,
        "lf_hf_ratio":   lf_hf_ratio,
        "lf_norm":       lf_norm,
        "hf_norm":       hf_norm,
        "spo2":          spo2,
    }


def run_prediction(ecg_array, spo2_val):
    """Raw ECG window → stress label + confidence."""
    # 1. Filter
    ecg_clean = bandpass_filter(ecg_array, fs=ECG_SAMPLE_RATE)

    # 2. R-peaks
    r_peaks = detect_r_peaks(ecg_clean, fs=ECG_SAMPLE_RATE)
    if len(r_peaks) < 4:
        print("⚠️  Not enough R-peaks detected")
        return None, None

    # 3. RR intervals (ms), remove physiologically impossible values
    rr_intervals = np.diff(r_peaks) / ECG_SAMPLE_RATE * 1000.0
    rr_intervals = rr_intervals[(rr_intervals > 300) & (rr_intervals < 2000)]
    if len(rr_intervals) < 3:
        print("⚠️  Not enough valid RR intervals")
        return None, None

    # 4. Extract features
    features = compute_hrv_features(rr_intervals, spo2=spo2_val)
    if features is None:
        return None, None

    # 5. Build vector in exact training order
    X        = np.array([[features[f] for f in FEATURE_NAMES]])
    X_scaled = scaler.transform(X)

    # 6. Predict
    pred       = model.predict(X_scaled)[0]
    proba      = model.predict_proba(X_scaled)[0]
    confidence = float(proba[pred])
    label      = "Stress" if pred == 1 else "No Stress"

    print(f"🧠 Prediction: {label} ({confidence:.2%} confidence)")
    return label, confidence


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/data", methods=["POST"])
def receive():
    global latest_data
    try:
        payload  = request.json
        bpm_val  = float(payload.get("bpm",  0))
        spo2_val = float(payload.get("spo2", 98))
        ecg_data = payload.get("ecg", [])

        with lock:
            latest_data["bpm"]  = bpm_val
            latest_data["spo2"] = spo2_val  # Always expose the latest SpO2 to React
            
            spo2_buffer.append(spo2_val)    # Store it in our rolling 60-second buffer

            if isinstance(ecg_data, list):
                ecg_buffer.extend(ecg_data)
                latest_data["ecg"] = ecg_data[-1] if ecg_data else 0
            else:
                ecg_buffer.append(float(ecg_data))
                latest_data['ecg'] = float(ecg_data)

            latest_data["buffered"] = len(ecg_buffer)
            buffer_full = (len(ecg_buffer) >= WINDOW_SAMPLES)

        if buffer_full:
            ecg_array = np.array(ecg_buffer)
            
            # 🔥 NEW: Calculate the average SpO2, ignoring zeros (no finger detected)
            valid_spo2_readings = [val for val in spo2_buffer if val > 0]
            if valid_spo2_readings:
                avg_spo2 = sum(valid_spo2_readings) / len(valid_spo2_readings)
            else:
                avg_spo2 = 98.0  # Fallback baseline if all readings were 0
                
            # Pass the stable average to the prediction model
            label, confidence = run_prediction(ecg_array, avg_spo2)
            
            with lock:
                latest_data["stress"]     = label
                latest_data["confidence"] = round(confidence, 4) if confidence else None

        return {"status": "ok", "buffered": len(ecg_buffer), "required": WINDOW_SAMPLES}

    except Exception as e:
        print(f"❌ Error: {e}")
        return {"status": "error", "msg": str(e)}, 500


@app.route("/data", methods=["GET"])
def get_data():
    with lock:
        return jsonify(latest_data)


@app.route("/status", methods=["GET"])
def status():
    with lock:
        return jsonify({
            "model_loaded": True,
            "buffer_filled": f"{len(ecg_buffer)}/{WINDOW_SAMPLES}",
            "last_prediction": latest_data["stress"],
            "confidence": latest_data["confidence"],
        })


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"📡 Flask server starting...")
    print(f"   Buffer: {WINDOW_SAMPLES} samples ({WINDOW_SECONDS}s @ {ECG_SAMPLE_RATE}Hz)")
    print(f"   First prediction fires after {WINDOW_SECONDS}s of ECG data\n")
    app.run(host="0.0.0.0", port=5000, threaded=True)
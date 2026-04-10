# 🧠 Smart Physiological Monitoring System - Stress Prediction



![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-Backend-green)
![React](https://img.shields.io/badge/React-Frontend-61DAFB)
![MicroPython](https://img.shields.io/badge/MicroPython-ESP32-yellow)

A real-time, end-to-end IoT and Machine Learning pipeline that detects human stress levels using physiological data. 

This project reads continuous electrocardiogram (ECG) and photoplethysmography (PPG) data on an ESP32 edge device, batches the high-frequency data, and transmits it to a Flask server. The server computes 19 medical-grade Heart Rate Variability (HRV) metrics over a 60-second sliding window and uses a pre-trained Machine Learning model to predict "Stress" or "No Stress." A React frontend provides a responsive, real-time medical dashboard.

---

## 📐 System Architecture

The system is split into three distinct layers:

### 1. Hardware & Edge Processing (MicroPython / ESP32)

* Interfaces with an **AD8232 ECG sensor** and a **MAX30102 Pulse Oximeter**.

* Calculates live BPM and SpO2 on the edge.

* Samples ECG at ~200Hz, batches the readings into an array in memory, and transmits the payload via HTTP POST exactly once per second to prevent network blocking.

### 2. The ML Server (Flask / Python)

* Acts as the computational brain. It maintains a 60-second sliding window (`deque`) of 12,000 ECG samples and a 60-second rolling buffer of SpO2 readings.

* Applies a bandpass filter to the ECG wave, detects precise R-peaks, and calculates 19 distinct time-domain, frequency-domain, and non-linear HRV features.

* Feeds the HRV features and the rolling average SpO2 into a pre-trained Scikit-Learn pipeline (`scaler.pkl` & `stress_model.pkl`) to generate a diagnosis and confidence score.

### 3. The Client Dashboard (React)

* A responsive dashboard that polls the server for data.

* Displays real-time sweeping charts for ECG, Pulse, and SpO2.

* Features dynamic UI highlights (red/green glowing borders) that trigger the moment the 60-second calibration phase is complete and a stress prediction is made.

---

## 🛠️ Hardware Requirements

* **Microcontroller:** ESP32 (or similar dual-core board)

* **Optical Sensor:** MAX30102 (I2C - *Note: Ambient light heavily affects the MAX30102. Shield the sensor during use for accurate SpO2 readings.*)

* **Electrical Sensor:** AD8232 (Analog) with standard 3-lead biometric pads

---

## 🚀 Installation & Setup

### 1. Flask Backend

```bash

# Navigate to backend folder
cd backend

# Install dependencies
pip install flask flask-cors numpy scipy joblib scikit-learn

# Ensure your models are placed correctly
# (e.g., 'model_output/stress_model.pkl' and 'model_output/scaler.pkl')

# Run the server
python app.py
```

### 2. ESP32 Edge Device

1. Flash your ESP32 with the latest MicroPython firmware.

2. Upload the `max30102.py` driver to the board.

3. Update the Wi-Fi credentials and `SERVER_URL` in `main.py` to match your local network and Flask IP.

4. Run `main.py`.



### 3. React Frontend

```bash

cd frontend

npm install

npm start # or npm run dev
```

## 📡 API Endpoints

### `POST /data`
Receives batched telemetry from the ESP32.

- Payload Example:
```JSON
{
  "bpm": 85,
  "spo2": 98,
  "ecg": [1600, 1612, 1604, ...]
}
```

Success Response: `{"status": "ok", "buffered": 12000, "required": 12000}`

### `GET /data`

Serves the latest buffered telemetry and AI prediction to the React frontend.

- Response Example:
```JSON

{
  "bpm": 85.0,
  "spo2": 98.0,
  "ecg": 1604,
  "stress": "Stress",
  "confidence": 0.8124,
  "buffered": 12000,
  "required": 12000
}
```

## 🧬 Data Science & Machine Learning Details 

The system does not rely on the MAX30102 for heart rate calculation during ML inference due to optical motion artifacts. Instead, it extracts the mean_hr directly from the electrical AD8232 signal for medical-grade precision.

The sliding window approach ensures that once the initial 60-second baseline is gathered, the model outputs a fresh, rolling prediction every 1 second based on the most recent 60 seconds of data. SpO2 values are averaged over the window (ignoring zero-values) to prevent sensor slip from triggering false stress anomalies.


from machine import ADC, Pin, I2C
from max30102 import MAX30102
import time
import network
import urequests

# ---------------- WIFI ----------------
ssid = "KAMY's Galaxy"
password = "47474747"
last_bpm = 0

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(ssid, password)

while not wifi.isconnected():
    pass

print("Connected:", wifi.ifconfig())

SERVER_URL = "http://10.14.92.61:5000/data"

# ---------------- ECG SETUP ----------------
ecg = ADC(Pin(36))
ecg.atten(ADC.ATTN_11DB)

lo_plus = Pin(32, Pin.IN)
lo_minus = Pin(33, Pin.IN)

# ---------------- MAX30102 SETUP ----------------
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = MAX30102(i2c)

print("System Ready")

# ---------------- FILTER ----------------
ir_buffer = []
red_buffer = []

def smooth(buf, val, size=5):
    buf.append(val)
    if len(buf) > size:
        buf.pop(0)
    return sum(buf) / len(buf)

def flush(sensor, n=5):
    for _ in range(n):
        sensor.read_fifo()

# ---------------- NETWORK ----------------
def send_data(bpm, spo2, ecg_batch_list):
    try:
        data = {
            # "bpm": int(bpm) if bpm else 0,
            # "spo2": int(spo2) if spo2 else 0,
            "ecg": ecg_batch_list
        }
        
        if last_bpm:
            data["bpm"] = int(last_bpm)
        if spo2 > 60:
            data["spo2"] = int(spo2)

        res = urequests.post(SERVER_URL, json=data)
        res.close()

        print("Sent:", data)

    except Exception as e:
        print("Send error:", e)

# ---------------- VARIABLES ----------------
ir_history = []
bpm_values = []
last_peak_time = 0

ecg_batch = []

ir_dc = 0
red_dc = 0

FINGER_THRESHOLD = 10000
state = "NO_FINGER"

# ---------------- TIMERS ----------------
last_vitals_send = time.ticks_ms()
last_ecg_send = time.ticks_ms()


# ---------------- SMOOTH ECG --------------
ecg_buffer = []

def smooth_ecg(val):
    ecg_buffer.append(val)
    if len(ecg_buffer) > 3:
        ecg_buffer.pop(0)
    return sum(ecg_buffer)/len(ecg_buffer)

# ---------------- MAIN LOOP ----------------
try:
    while True:

        # ===== ECG READ =====
        if lo_plus.value() == 1 or lo_minus.value() == 1:
            ecg_val = 0  # leads off
        else:
            # ecg_val = ecg.read()
            
            ecg_val = smooth_ecg(ecg.read())

        ecg_batch.append(int(ecg_val))
        # ===== MAX30102 READ =====
        flush(sensor)
        red, ir = sensor.read_fifo()

        # -------- NO FINGER --------
        if ir < FINGER_THRESHOLD:
            if state != "NO_FINGER":
                print("No Finger Detected")
                state = "NO_FINGER"

            ir_history.clear()
            bpm_values.clear()
            last_peak_time = 0

            bpm = 0
            spo2 = 0

        else:
            if state == "NO_FINGER":
                print("Processing...")
                state = "PROCESSING"

            # -------- SMOOTH --------
            ir = smooth(ir_buffer, ir)
            red = smooth(red_buffer, red)

            # -------- HISTORY --------
            ir_history.append(ir)
            if len(ir_history) > 10:
                ir_history.pop(0)

            bpm = None

            # -------- PEAK DETECTION --------
            if len(ir_history) >= 3:
                if ir_history[-2] > ir_history[-3] and ir_history[-2] > ir_history[-1]:
                    now = time.ticks_ms()

                    if last_peak_time != 0:
                        diff = time.ticks_diff(now, last_peak_time)

                        if 300 < diff < 2000:
                            bpm_values.append(60000 / diff)

                            if len(bpm_values) > 5:
                                bpm_values.pop(0)

                            bpm = sum(bpm_values) / len(bpm_values)

                    last_peak_time = now
                    
            if bpm is not None:
                last_bpm = bpm

            # -------- SpO2 --------
            ir_dc = (ir_dc * 0.9) + (ir * 0.1)
            red_dc = (red_dc * 0.9) + (red * 0.1)

            ir_ac = ir - ir_dc
            red_ac = red - red_dc

            if ir_ac != 0 and ir_dc != 0:
                R = (red_ac / red_dc) / (ir_ac / ir_dc)
                spo2 = 104 - (17 * R)
                spo2 = max(0, min(100, spo2))
            else:
                spo2 = 0

        # ===== SEND ECG FAST (100 ms) =====
        if time.ticks_diff(time.ticks_ms(), last_ecg_send) > 1000:
            send_data(bpm if bpm else 0, spo2, ecg_batch)
            ecg_batch = []
            last_ecg_send = time.ticks_ms()

        # ===== SEND BPM/SPO2 SLOW (3 sec) =====
        if bpm and time.ticks_diff(time.ticks_ms(), last_vitals_send) > 3000:
            print("Vitals:", int(bpm), int(spo2))
            last_vitals_send = time.ticks_ms()

        time.sleep_ms(5)

except KeyboardInterrupt:
    print("\nStopped safely.")

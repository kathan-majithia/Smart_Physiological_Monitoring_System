from machine import I2C, Pin
from max30102 import MAX30102
import time
import network
import socket
import json
import urequests

ssid = "XYZ"
password = "********"

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(ssid,password)

while not wifi.isconnected():
    pass

print("Connected: ",wifi.ifconfig())

SERVER_IP = "192.168.x.x"
PORT = 5000

# -------- SETUP --------
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = MAX30102(i2c)

print("System Ready")

# -------- FILTER --------
ir_buffer = []
red_buffer = []

def smooth(buf, val, size=5):
    buf.append(val)
    if len(buf) > size:
        buf.pop(0)
    return sum(buf) / len(buf)

# -------- FIFO FLUSH --------
def flush(sensor, n=5):
    for _ in range(n):
        sensor.read_fifo()
        
# -------- SEND FUNCTION (NETWORKING) --------
def send_data(bpm,spo2):
    try:
        url = "http://10.14.92.61:5000/data"
        data = {
            "bpm":bpm,
            "spo2":spo2
        }
        res = urequests.post(url,json=data)
        res.close()
        
        print("Sent : ",data)
        
    except Exception as e:
        print("Send error : ",e)

# -------- VARIABLES --------
ir_history = []
last_peak_time = 0
bpm_values = []

ir_dc = 0
red_dc = 0

FINGER_THRESHOLD = 10000

# -------- STATE --------
state = "NO_FINGER"

last_send = time.time()

try:
    while True:
        flush(sensor)
        red, ir = sensor.read_fifo()

        # -------- NO FINGER --------
        if ir < FINGER_THRESHOLD:
            if state != "NO_FINGER":
                print("No Finger Detected")
                state = "NO_FINGER"

            # reset everything
            ir_history.clear()
            bpm_values.clear()
            last_peak_time = 0
            time.sleep(0.1)
            continue

        # -------- FINGER PRESENT --------
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

        # -------- READY STATE --------
        if bpm is not None:
            if state != "READY":
                state = "READY"

            # print("BPM:", int(bpm), "| SpO2:", int(spo2), "%")
            
            now = time.time()
            
            if now - last_send >= 3:
                send_data(int(bpm),int(spo2))
                # print("Sent: ",bpm,spo2)
                last_send = now

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopped safely.")

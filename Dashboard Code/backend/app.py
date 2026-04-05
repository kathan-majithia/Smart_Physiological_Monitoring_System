from flask import Flask, jsonify, request
from flask_cors import CORS
import socket
import threading
import json

app = Flask(__name__)

CORS(app)

latest_data = {
    "bpm": 0,
    "spo2": 0
}

# Receive from ESP
@app.route("/data",methods=["POST"])
def receive():
    global latest_data

    try:
        latest_data = request.json
        print("Received: ",latest_data)
        return {"status":"ok"}
    except Exception as e:
        print("Error : ",e)
        return {"status":"error"}

# -------- API FOR REACT --------
@app.route("/data", methods=["GET"])
def get_data():
    return jsonify(latest_data)

app.run(host="0.0.0.0", port=5000)
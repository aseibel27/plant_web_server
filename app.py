from flask import Flask, request, render_template, send_file, jsonify
import csv
import os
from datetime import datetime
import requests
from dotenv import load_dotenv

app = Flask(__name__)

# Set NodeMCU's IP address
load_dotenv()
NODEMCU_IP = os.getenv("NODEMCU_IP")

# Log file path
LOG_PATH = "hourly_log.csv"

# Store latest moisture readings
latest_readings = {}

@app.route('/')
def index():
    return render_template('index.html')

# Serve static files
@app.route('/style.css')
def style():
    return app.send_static_file('style.css')

@app.route('/main.js')
def main_js():
    return app.send_static_file('main.js')

@app.route('/chart.js')
def chart_js():
    return app.send_static_file('chart.js')

# Receive real-time moisture data from NodeMCU
@app.route('/moisture', methods=['POST'])
def receive_moisture():
    global latest_readings
    data = request.json
    latest_readings = data
    print("Moisture:", data)

    # Optionally log hourly average
    now = datetime.now()
    if now.minute == 0 and now.second < 5:  # Log only once per hour
        log_hourly_average(now, data)

    return jsonify({'status': 'ok'})

def log_hourly_average(now, data):
    # Write to CSV file
    header = ['date', 'hour', 'value1', 'value2', 'value3', 'value4']
    row = [now.strftime('%Y-%m-%d'), now.strftime('%H')]
    row += [data.get(f'moist{i+1}', -1) for i in range(4)]

    exists = os.path.exists(LOG_PATH)
    with open(LOG_PATH, 'a', newline='') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(header)
        writer.writerow(row)
    print("Logged hourly average.")

# Send a command to the NodeMCU to turn pump on/off
@app.route('/on/<int:id>', methods=['POST'])
@app.route('/off/<int:id>', methods=['POST'])
def control_pump(id):
    if id < 0 or id > 3:
        return "Invalid pump ID", 400

    state = request.path.startswith("/on")
    try:
        response = requests.post(f"http://{NODEMCU_IP}/set_pump", json={"id": id, "on": state}, timeout=2)
        return f"Pump {id} {'ON' if state else 'OFF'} - NodeMCU responded with {response.status_code}"
    except requests.RequestException as e:
        return f"Failed to contact NodeMCU: {e}", 500

@app.route('/hourly_log.csv')
def download_log():
    if not os.path.exists(LOG_PATH):
        return "No log file found", 404
    return send_file(LOG_PATH, as_attachment=True)

@app.route('/clear_log')
def clear_log():
    with open(LOG_PATH, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'hour', 'value1', 'value2', 'value3', 'value4'])
    return "Log cleared."

@app.route('/hourly_json')
def hourly_json():
    if not os.path.exists(LOG_PATH):
        return jsonify({"error": "No log available"}), 404

    with open(LOG_PATH, newline='') as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        times, p1, p2, p3, p4 = [], [], [], [], []
        for row in reader:
            time_str = f"{row[0]} {row[1]}:00"
            times.append(time_str)
            p1.append(int(row[2]))
            p2.append(int(row[3]))
            p3.append(int(row[4]))
            p4.append(int(row[5]))

    return jsonify({
        "time": times,
        "plant1": p1,
        "plant2": p2,
        "plant3": p3,
        "plant4": p4
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

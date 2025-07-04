from flask import Flask, request, jsonify, render_template, send_file
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
import threading
import time
import os
import csv
import requests
from dotenv import load_dotenv
import traceback

load_dotenv()
NODEMCU_IP = os.getenv("NODEMCU_IP")

app = Flask(__name__)

# Calibration bounds (editable without reflashing firmware)
MOISTURE_CALIBRATION = {
    0: (714, 302),  # Sensor 1: (dry, wet)
    1: (687, 288),  # replaced sensor 2 on 7/4/25
    2: (713, 295), 
    3: (694, 293),
}

def map_moisture(raw, dry, wet):
    if raw < wet:
        return 100
    elif raw > dry:
        return 0
    else:
        return int((dry - raw) * 100 / (dry - wet))

# === In-Memory Rolling Buffers ===
second_data = [deque(maxlen=60) for _ in range(6)]  # moisture per second
minute_data = [deque(maxlen=60) for _ in range(6)]  # 1 avg per min
hour_data   = [deque(maxlen=24) for _ in range(6)]  # 1 avg per hour
day_data    = [deque(maxlen=60) for _ in range(6)]  # 1 avg per day (last 60 days)

lock = Lock()
last_second = last_minute = last_hour = last_day = None

HOURLY_LOG = os.path.join("logs", "hourly_log.csv")
DAILY_LOG = os.path.join("logs", "daily_log.csv")

# For static file serving convenience
STATIC_FILES = ['style.css', 'main.js', 'chart.js']

# === NodeMCU online status tracking ===
last_post_time = None
node_status = "offline"
status_lock = Lock()

# === Helper: Save to CSV ===
def save_csv_row(filepath, header, row):
    exists = os.path.exists(filepath)
    with open(filepath, 'a', newline='') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(header)
        writer.writerow(row)

@app.route('/ping')
def ping():
    return "OK", 200

# === Receive moisture data from ESP8266 (POST) ===
@app.route('/moisture', methods=['POST'])
def receive_moisture():
    global last_second, last_minute, last_hour, last_day, last_post_time, node_status
    now = datetime.now()

    data = request.json or {}
    print("Received POST data:", data)

    # Store raw data for access via /raw
    global latest_raw_readings
    latest_raw_readings = data.copy()

    sensors = []
    for i in range(4):
        raw = data.get(f"moist{i+1}", -1)
        if raw == -1:
            sensors.append(-1)
        else:
            dry, wet = MOISTURE_CALIBRATION[i]
            mapped = map_moisture(raw, dry, wet)

            sensors.append(mapped)
    sensors.append(data.get("temp", -1))
    sensors.append(data.get("hum", -1))

    with lock:
        # === Update seconds buffer ===
        if last_second is not None:
            missing = int((now - last_second).total_seconds()) - 1
            for _ in range(missing):
                for i in range(6):
                    second_data[i].append(-1)

        for i in range(6):
            second_data[i].append(sensors[i])
        last_second = now

        if last_minute is not None and now.minute != last_minute.minute:
            for i in range(6):
                valid = [v for v in second_data[i] if v >= 0]
                avg = sum(valid) // len(valid) if valid else -1
                minute_data[i].append(avg)
            last_minute = now

            if last_hour is not None and now.hour != last_hour.hour:
                hourly = []
                for i in range(6):
                    valid = [v for v in minute_data[i] if v >= 0]
                    avg = sum(valid) // len(valid) if valid else -1
                    hour_data[i].append(avg)
                    hourly.append(avg)
                timestamp = now.strftime('%Y-%m-%d %H:00')
                save_csv_row(HOURLY_LOG, ['datetime','plant1','plant2','plant3','plant4','temp','hum'], [timestamp] + hourly)
                last_hour = now

                if last_day is not None and now.day != last_day.day:
                    daily = []
                    for i in range(6):
                        valid = [v for v in hour_data[i] if v >= 0]
                        avg = sum(valid) // len(valid) if valid else -1
                        day_data[i].append(avg)
                        daily.append(avg)
                    save_csv_row(DAILY_LOG, ['date','plant1','plant2','plant3','plant4','temp','hum'], [now.strftime('%Y-%m-%d')] + daily)
                    last_day = now

        if last_minute is None:
            last_minute = now
        if last_hour is None:
            last_hour = now
        if last_day is None:
            last_day = now

    # Update last_post_time and set online if offline
    with status_lock:
        last_post_time = now
        if node_status == "offline":
            node_status = "online"

    return jsonify({'status': 'ok'})

# === Get latest raw moisture readings (GET) ===
@app.route('/raw', methods=['GET'])
def get_raw():
    return jsonify(latest_raw_readings)

# === Get latest moisture readings (GET) ===
@app.route('/moisture', methods=['GET'])
def get_moisture():
    with lock:
        return jsonify({
            f'moist{i+1}': second_data[i][-1] if len(second_data[i]) > 0 else -1
            for i in range(4)
        } | {
            "temp": second_data[4][-1] if len(second_data[4]) > 0 else -1,
            "hum":  second_data[5][-1] if len(second_data[5]) > 0 else -1,
        })

# === History Retrieval for Charts ===
@app.route('/history')
def get_history():
    q = request.args.get('type', 'seconds')
    with lock:
        if q == 'seconds':
            time = list(range(60))
            data = {f'sensor{i+1}': list(reversed(second_data[i])) for i in range(6)}
            return jsonify({'time': time, **data})

        elif q == 'minutes':
            time = list(range(60))
            data = {f'sensor{i+1}': list(reversed(minute_data[i])) for i in range(6)}
            return jsonify({'time': time, **data})

        elif q == 'hours':
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            hours = [(now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00') for i in reversed(range(60))]
            values_by_time = {h: [-1]*6 for h in hours}

            if os.path.exists(HOURLY_LOG):
                with open(HOURLY_LOG, newline='') as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader:
                        time_str = row[0]
                        if time_str in values_by_time:
                            values_by_time[time_str] = [int(v) if v else -1 for v in row[1:7]]

            return jsonify({
                'time': hours,
                **{f'sensor{i+1}': [values_by_time[h][i] for h in hours] for i in range(6)}
            })

        elif q == 'days':
            today = datetime.now().date()
            days = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in reversed(range(60))]
            values_by_date = {d: [-1]*6 for d in days}

            if os.path.exists(DAILY_LOG):
                with open(DAILY_LOG, newline='') as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader:
                        date_str = row[0]
                        if date_str in values_by_date:
                            values_by_date[date_str] = [int(v) if v else -1 for v in row[1:7]]

            return jsonify({
                'time': days,
                **{f'sensor{i+1}': [values_by_date[d][i] for d in days] for i in range(6)}
            })

        else:
            return jsonify({'error': 'Invalid type'}), 400

# === Load CSV History ===
def read_csv_last_n(path, maxlen):
    if not os.path.exists(path):
        return [], [[] for _ in range(4)]

    times, values = [], []
    with open(path, newline='') as f:
        reader = list(csv.reader(f))
        reader = reader[1:]
        for row in reader[-maxlen:]:
            times.append(row[0])
            values.append([int(v) if v else -1 for v in row[1:5]])
    return times, values

# === Forward pump control command to NodeMCU ===
@app.route('/set_pump', methods=['POST'])
def control_pump():
    data = request.json
    if not data or 'id' not in data or 'on' not in data:
        return "Invalid JSON", 400

    pump_id = data['id']
    state = data['on']

    if not isinstance(pump_id, int) or pump_id < 0 or pump_id > 3:
        return "Invalid pump ID", 400

    try:
        response = requests.post(
            f"http://{NODEMCU_IP}/set_pump",
            json={"id": pump_id, "on": state},
            timeout=2
        )
        return jsonify({'status': 'ok', 'message': f"Pump {pump_id} {'ON' if state else 'OFF'} - NodeMCU responded with {response.status_code}"})
    except requests.RequestException as e:
        print("Error contacting NodeMCU:")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Failed to contact NodeMCU: {e}"}), 500

# === Serve main page ===
@app.route('/')
def index():
    return render_template('index.html')

# === Serve static assets ===
@app.route('/<path:filename>')
def static_files(filename):
    if filename in STATIC_FILES:
        return app.send_static_file(filename)
    else:
        return "File not found", 404

# === Download hourly log ===
@app.route('/hourly_log.csv')
def download_log():
    if not os.path.exists(HOURLY_LOG):
        return "No log file found", 404
    return send_file(HOURLY_LOG, as_attachment=True)

# === Clear hourly log ===
@app.route('/clear_log')
def clear_log():
    with open(HOURLY_LOG, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['datetime','plant1','plant2','plant3','plant4','temp','hum'])
    return "Log cleared."

# === NodeMCU status endpoint ===
@app.route('/status')
def get_status():
    with status_lock:
        return jsonify({'status': node_status})

# === Background thread to update online/offline status ===
def status_watcher():
    global node_status, last_post_time
    while True:
        with status_lock:
            if last_post_time is None or (datetime.now() - last_post_time).total_seconds() > 1.1:
                node_status = "offline"
        time.sleep(0.5)

threading.Thread(target=status_watcher, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

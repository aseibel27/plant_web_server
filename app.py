from flask import Flask, request, jsonify, render_template, send_file
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
import os
import csv
import requests
from dotenv import load_dotenv

load_dotenv()
NODEMCU_IP = os.getenv("NODEMCU_IP")

app = Flask(__name__)

# === In-Memory Rolling Buffers ===
second_data = [deque(maxlen=60) for _ in range(4)]  # moisture per second
minute_data = [deque(maxlen=60) for _ in range(4)]  # 1 avg per min
hour_data   = [deque(maxlen=24) for _ in range(4)]  # 1 avg per hour
day_data    = [deque(maxlen=60) for _ in range(4)]  # 1 avg per day (last 60 days)

lock = Lock()
last_second = last_minute = last_hour = last_day = None

HOURLY_LOG = os.path.join("logs", "hourly_log.csv")
DAILY_LOG = os.path.join("logs", "daily_log.csv")

# For static file serving convenience
STATIC_FILES = ['style.css', 'main.js', 'chart.js']

# Store the latest moisture readings for quick GET access
latest_readings = {}

# === Helper: Save to CSV ===
def save_csv_row(filepath, header, row):
    exists = os.path.exists(filepath)
    with open(filepath, 'a', newline='') as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(header)
        writer.writerow(row)

# === Receive moisture data from ESP8266 (POST) ===
@app.route('/moisture', methods=['POST'])
def receive_moisture():
    global last_second, last_minute, last_hour, last_day
    now = datetime.now()  # ✅ capture time at start

    data = request.json or {}
    moist = [data.get(f"moist{i+1}", -1) for i in range(4)]

    with lock:
        # === Update seconds buffer ===
        if last_second is not None:
            missing = int((now - last_second).total_seconds()) - 1
            for _ in range(missing):
                for i in range(4):
                    second_data[i].append(-1)

        for i in range(4):
            second_data[i].append(moist[i])
        last_second = now

        # === Update minutes buffer if minute has changed ===
        if last_minute is not None and now.minute != last_minute.minute:
            for i in range(4):
                valid = [v for v in second_data[i] if v >= 0]
                avg = sum(valid) // len(valid) if valid else -1
                minute_data[i].append(avg)
            last_minute = now

            # === Update hourly buffer if hour has changed ===
            if last_hour is not None and now.hour != last_hour.hour:
                hourly = []
                for i in range(4):
                    valid = [v for v in minute_data[i] if v >= 0]
                    avg = sum(valid) // len(valid) if valid else -1
                    hour_data[i].append(avg)
                    hourly.append(avg)
                timestamp = now.strftime('%Y-%m-%d %H:00')
                save_csv_row(HOURLY_LOG, ['datetime','plant1','plant2','plant3','plant4'], [timestamp] + hourly)
                last_hour = now

                # === Update daily buffer if day has changed ===
                if last_day is not None and now.day != last_day.day:
                    daily = []
                    for i in range(4):
                        valid = [v for v in hour_data[i] if v >= 0]
                        avg = sum(valid) // len(valid) if valid else -1
                        day_data[i].append(avg)
                        daily.append(avg)
                    save_csv_row(DAILY_LOG, ['date','plant1','plant2','plant3','plant4'], [now.strftime('%Y-%m-%d')] + daily)
                    last_day = now

        # === Set initial reference times if still None ===
        if last_minute is None:
            last_minute = now
        if last_hour is None:
            last_hour = now
        if last_day is None:
            last_day = now

    return jsonify({'status': 'ok'})

# === Get latest moisture readings (GET) ===
@app.route('/moisture', methods=['GET'])
def get_moisture():
    with lock:
        return jsonify({
            f'moist{i+1}': second_data[i][-1] if len(second_data[i]) > 0 else -1
            for i in range(4)
        })

# === History Retrieval for Charts ===
@app.route('/history')
def get_history():
    q = request.args.get('type', 'seconds')
    with lock:
        if q == 'seconds':
            time = list(range(60))
            data = {f'plant{i+1}': list(reversed(second_data[i])) for i in range(4)}
            return jsonify({'time': time, **data})

        elif q == 'minutes':
            time = list(range(60))
            data = {f'plant{i+1}': list(reversed(minute_data[i])) for i in range(4)}
            return jsonify({'time': time, **data})

        elif q == 'hours':
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            hours = [(now - timedelta(hours=i)).strftime('%Y-%m-%d %H:00') for i in reversed(range(60))]
            values_by_time = {h: [-1, -1, -1, -1] for h in hours}

            if os.path.exists(HOURLY_LOG):
                with open(HOURLY_LOG, newline='') as f:
                    reader = csv.reader(f)
                    next(reader)  # skip header
                    for row in reader:
                        time_str = row[0]
                        if time_str in values_by_time:
                            values_by_time[time_str] = [int(v) if v else -1 for v in row[1:5]]

            return jsonify({
                'time': hours,
                **{f'plant{i+1}': [values_by_time[h][i] for h in hours] for i in range(4)}
            })

        elif q == 'days':
            today = datetime.now().date()
            days = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in reversed(range(60))]
            values_by_date = {d: [-1, -1, -1, -1] for d in days}

            if os.path.exists(DAILY_LOG):
                with open(DAILY_LOG, newline='') as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader:
                        date_str = row[0]
                        if date_str in values_by_date:
                            values_by_date[date_str] = [int(v) if v else -1 for v in row[1:5]]

            return jsonify({
                'time': days,
                **{f'plant{i+1}': [values_by_date[d][i] for d in days] for i in range(4)}
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
        reader = reader[1:]  # skip header
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
        writer.writerow(['datetime','plant1','plant2','plant3','plant4'])
    return "Log cleared."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

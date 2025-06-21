#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <DHT.h>
#define DHTTYPE DHT22

#include "secrets.h" // WiFi credentials and server info

// === Constants ===
const int NUM_PLANTS = 4;
const int NUM_SELECTORS = 3;
const int NUM_SENSORS = 6;

const int pumpRelayPins[NUM_PLANTS] = {D2, D5, D6, D7};  // Pump control relays
const int selectorPins[NUM_SELECTORS] = {D0, D1, D3};    // MUX control pins
const int dhtPin = D4;    // Digital input for DHT22
const int analogPin = A0; // Analog input for moist sensors

// === MUX selection matrix ===
const int muxSelections[NUM_PLANTS][NUM_SELECTORS] = {
  {LOW, LOW, LOW}, {HIGH, LOW, LOW},
  {LOW, HIGH, LOW}, {HIGH, HIGH, LOW},
};

// === Sensor Data ===
int sensorValues[NUM_SENSORS];  // 4 moisture, 1 temp, 1 hum

// === DHT Class ===
DHT dht(dhtPin, DHTTYPE);

// === Web server ===
ESP8266WebServer server(80);

// === Find Flask Host ===
struct FlaskTarget {
  const char* host;
  int port;
};

FlaskTarget activeFlask = {nullptr, 0};

// === Setup ===
void setup() {
  Serial.begin(115200);

  // Set pin modes
  for (int i = 0; i < NUM_PLANTS; i++) {
    pinMode(pumpRelayPins[i], OUTPUT);
    digitalWrite(pumpRelayPins[i], HIGH); // OFF = HIGH
  }
  for (int i = 0; i < NUM_SELECTORS; i++) {
    pinMode(selectorPins[i], OUTPUT);
    digitalWrite(selectorPins[i], LOW);
  }
  pinMode(dhtPin, INPUT);

  // Connect Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());

  // Choose active flask server
  if (testFlaskHost({PRIMARY_FLASK_HOST, PRIMARY_FLASK_PORT})) {
    activeFlask = {PRIMARY_FLASK_HOST, PRIMARY_FLASK_PORT};
    Serial.println("Using primary Flask server.");
  } else if (testFlaskHost({BACKUP_FLASK_HOST, BACKUP_FLASK_PORT})) {
    activeFlask = {BACKUP_FLASK_HOST, BACKUP_FLASK_PORT};
    Serial.println("Primary failed, using backup Flask server.");
  } else {
    Serial.println("No reachable Flask server found.");
  }

  // Setup time
  configTime(0, 0, "pool.ntp.org");
  setenv("TZ", "EST5EDT,M3.2.0/2,M11.1.0/2", 1);
  tzset();

  // Setup web endpoint
  server.on("/set_pump", HTTP_POST, handlePumpControl);
  server.begin();

  // Initialize DHT
  dht.begin();
}

// === Main Loop ===
unsigned long lastSent = 0;
void loop() {
  server.handleClient();

  if (millis() - lastSent > 1000) {
    ReadMoisture();
    ReadDHT();
    LogSensorValues();
    SendToFlask(activeFlask);
    lastSent = millis();
  }
}

// === Read All 4 Moisture Channels ===
void ReadMoisture() {
  for (int i = 0; i < NUM_PLANTS; i++) {
    // Select MUX channel
    for (int j = 0; j < NUM_SELECTORS; j++) {
      digitalWrite(selectorPins[j], muxSelections[i][j]);
    }
    delay(10);

    sensorValues[i] = analogRead(analogPin);  // Raw value
  }
}

// === Read DHT22 ===
void ReadDHT() {
  delay(10);  // Let signal stabilize

  float t = dht.readTemperature(true);
  float h = dht.readHumidity();

  if (!isnan(t)) {
    t = constrain(t, 0, 120);  // constrain to valid range
    sensorValues[4] = (int)t;
  } else {
    sensorValues[4] = -1;
  }

  if (!isnan(h)) {
    h = constrain(h, 0, 100);  // constrain to valid range
    sensorValues[5] = (int)h;
  } else {
    sensorValues[5] = -1;
  }
}

// === Log Sensor Values ===
void LogSensorValues() {
  Serial.printf("Moist: %d %d %d %d | Temp: %d | Humidity: %d\n",
    sensorValues[0], sensorValues[1], sensorValues[2], sensorValues[3],
    sensorValues[4], sensorValues[5]);
}

// === Send Sensor Data to Flask ===
void SendToFlask() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (activeFlask.host == nullptr) return;  // No valid server

  SendToFlask(activeFlask);
}

// === Send to Flask Host ===
bool SendToFlask(FlaskTarget flask) {
  if (WiFi.status() != WL_CONNECTED) return false;
  if (activeFlask.host == nullptr) return false;  // No valid server
  WiFiClient client;
  HTTPClient http;

  String url = String("http://") + flask.host + ":" + String(flask.port) + "/moisture";
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<200> doc;
  for (int i = 0; i < NUM_PLANTS; i++) {
    doc["moist" + String(i + 1)] = sensorValues[i];
  }
  doc["temp"] = sensorValues[4];
  doc["hum"]  = sensorValues[5];

  String json;
  serializeJson(doc, json);

  int code = http.POST(json);
  Serial.printf("POST /moisture => code %d\n", code);
  http.end();

  return code >= 200 && code < 300;  // Success if HTTP 2xx
}

// === Try Flask Host ===
bool testFlaskHost(FlaskTarget flask) {
  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + flask.host + ":" + String(flask.port) + "/ping";  // or "/moisture" if you prefer

  http.begin(client, url);
  int code = http.GET();  // GET request to check server availability
  http.end();

  return code > 0 && code < 500;  // Accept 2xx and 3xx as success
}

// === Handle Pump Control ===
void handlePumpControl() {
  StaticJsonDocument<128> doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));

  if (error) {
    server.send(400, "text/plain", "Bad JSON");
    return;
  }

  int id = doc["id"];
  bool on = doc["on"];

  if (id < 0 || id >= NUM_PLANTS) {
    server.send(400, "text/plain", "Invalid pump ID");
    return;
  }

  digitalWrite(pumpRelayPins[id], on ? LOW : HIGH);
  Serial.printf("Pump %d turned %s\n", id, on ? "ON" : "OFF");
  server.send(200, "text/plain", "OK");
}

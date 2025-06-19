#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <DHT.h>
#define DHTTYPE DHT22
#define DHTPIN D4
DHT dht(DHTPIN, DHTTYPE);       // We'll re-init this temporarily in code when needed

#include "secrets.h" // Wifi credentials and server info

// === Pins ===
const int outputPins[] = {D2, D5, D6, D7};  // Pump control relays
const int selectorPins[] = {D0, D1, D3};    // MUX control pins
const int sensorPin = A0;

// === MUX selection matrix ===
const int muxSelections[4][3] = {
  {LOW, LOW, LOW}, {HIGH, LOW, LOW},
  {LOW, HIGH, LOW}, {HIGH, HIGH, LOW},
};

// === Sensor Data ===
int sensorValue[6];

// === Web server to receive pump commands ===
ESP8266WebServer server(80);

// === Setup ===
void setup() {
  Serial.begin(115200);

  // Set pin modes
  for (int i = 0; i < 4; i++) {
    pinMode(outputPins[i], OUTPUT);
    digitalWrite(outputPins[i], HIGH); // OFF = HIGH
  }
  for (int i = 0; i < 3; i++) {
    pinMode(selectorPins[i], OUTPUT);
    digitalWrite(selectorPins[i], LOW);
  }
  pinMode(DHTPIN, INPUT);

  // Connect Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());

  // Setup time
  configTime(0, 0, "pool.ntp.org");
  setenv("TZ", "EST5EDT,M3.2.0/2,M11.1.0/2", 1);
  tzset();

  // Setup endpoint to receive pump commands
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
    sendToFlask();
    lastSent = millis();
  }
}

// === Read All 4 Moisture Channels ===
void ReadMoisture() {
  for (int i = 0; i < 4; i++) {
    for (int j = 0; j < 3; j++) {
      digitalWrite(selectorPins[j], muxSelections[i][j]);
    }
    delay(10);

    int raw = analogRead(sensorPin);
    int mappedVal;
    switch (i) {
      case 0: mappedVal = map(raw, 805, 327, 0, 100); break;
      case 1: mappedVal = map(raw, 811, 326, 0, 100); break;
      case 2: mappedVal = map(raw, 813, 325, 0, 100); break;
      case 3: mappedVal = map(raw, 708, 300, 0, 100); break;
    }
    sensorValue[i] = constrain(mappedVal, 0, 100);
  }
}

void ReadDHT() {
  delay(10);  // Let signal stabilize

  float t = dht.readTemperature(true);
  Serial.printf("t: %.1f",t);
  float h = dht.readHumidity();
  Serial.printf("h: %.1f",h);
  sensorValue[4] = isnan(t) ? NAN : (int)t;
  sensorValue[5] = isnan(h) ? NAN : (int)h;

  Serial.printf("Moist: %d %d %d %d | Temp: %.1f°C | Humidity: %.1f%%\n",
    (int)sensorValue[0], (int)sensorValue[1], (int)sensorValue[2], (int)sensorValue[3],
    sensorValue[4], sensorValue[5]);
}

// === Send Sensor Data to Flask ===
void sendToFlask() {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;

  String url = String("http://") + FLASK_HOST + ":" + FLASK_PORT + "/moisture";
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<200> doc;
  doc["moist1"] = sensorValue[0];
  doc["moist2"] = sensorValue[1];
  doc["moist3"] = sensorValue[2];
  doc["moist4"] = sensorValue[3];
  doc["temp"] = sensorValue[4];
  doc["hum"] = sensorValue[5];

  String json;
  serializeJson(doc, json);

  int code = http.POST(json);
  Serial.printf("POST /moisture => code %d\n", code);
  http.end();
}

// === Handle Pump Control from Flask ===
void handlePumpControl() {
  StaticJsonDocument<128> doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));

  if (error) {
    server.send(400, "text/plain", "Bad JSON");
    return;
  }

  int id = doc["id"];
  bool on = doc["on"];

  if (id < 0 || id >= 4) {
    server.send(400, "text/plain", "Invalid pump ID");
    return;
  }

  digitalWrite(outputPins[id], on ? LOW : HIGH);
  Serial.printf("Pump %d turned %s\n", id, on ? "ON" : "OFF");
  server.send(200, "text/plain", "OK");
}

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// =====================================================
// WIFI LAPTOP HOTSPOT
// =====================================================

#include "wifi_secrets.h"

// IP cố định của ESP32
IPAddress LOCAL_IP(192, 168, 137, 115);
IPAddress GATEWAY(192, 168, 137, 1);
IPAddress SUBNET(255, 255, 255, 0);

const uint16_t SERVER_PORT = 5000;

WiFiServer server(SERVER_PORT);
WiFiClient pythonClient;

// =====================================================
// PIN
// =====================================================

#define FLEX1_PIN 32
#define FLEX2_PIN 33
#define FLEX3_PIN 34
#define FLEX4_PIN 35
#define FLEX5_PIN 36

// flex1..5: thumb, index, middle, ring, little finger.
const size_t FLEX_COUNT = 5;
const int FLEX_PINS[FLEX_COUNT] = {
  FLEX1_PIN, FLEX2_PIN, FLEX3_PIN, FLEX4_PIN, FLEX5_PIN
};

#define LCD_SDA 21
#define LCD_SCL 22

#define MPU_SDA 27
#define MPU_SCL 26

// =====================================================
// LCD + MPU
// =====================================================

LiquidCrystal_I2C lcd(0x27, 16, 2);

TwoWire MPUWire = TwoWire(1);
Adafruit_MPU6050 mpu;

// =====================================================
// SAMPLE
// =====================================================

// RAW5_100 requests 100 Hz for calibrated 1.5-second gesture trials.
// Older RAW5/RAW2 clients keep their 25 Hz acquisition rate.
unsigned long sampleInterval = 40;

unsigned long lastSampleTime = 0;
unsigned long startTime = 0;

// =====================================================
// FLEX
// =====================================================

int prevFlex[FLEX_COUNT] = {0};
float dFlexHistory[FLEX_COUNT][3] = {};

int historyIndex = 0;

// =====================================================
// NHAN LENH PYTHON
// =====================================================

// Keep command storage bounded. Oversized commands are discarded through newline.
char receiveBuffer[96] = {0};
size_t receiveLength = 0;
bool discardCommand = false;
bool clientConnected = false;
bool recordingActive = false;
bool rawProtocolV2 = false;
bool rawProtocolV5 = false;
bool aiFresh = false;
bool sequenceResultLatched = false;
bool continuousMode = false;
unsigned long lastRunPacket = 0;
unsigned long lastAIResult = 0;
const unsigned long AI_TIMEOUT = 5000;

bool wifiOnline = false;
bool wifiAttemptStarted = false;
unsigned long lastWiFiAttempt = 0;
unsigned long wifiRetryInterval = 10000;
const unsigned long MAX_WIFI_RETRY_INTERVAL = 30000;

const bool DEBUG_SENSOR = false;

// =====================================================
// LCD
// =====================================================

void showLCD(const char* line1, const char* line2)
{
  static char previousLine1[17] = {0};
  static char previousLine2[17] = {0};
  char visibleLine1[17];
  char visibleLine2[17];
  snprintf(visibleLine1, sizeof(visibleLine1), "%.16s", line1);
  snprintf(visibleLine2, sizeof(visibleLine2), "%.16s", line2);
  if (strcmp(previousLine1, visibleLine1) == 0 &&
      strcmp(previousLine2, visibleLine2) == 0)
  {
    return;
  }
  strcpy(previousLine1, visibleLine1);
  strcpy(previousLine2, visibleLine2);
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(visibleLine1);
  lcd.setCursor(0, 1);
  lcd.print(visibleLine2);
}

// =====================================================
// DOC FLEX TRUNG BINH 3 LAN
// =====================================================

int readFlexAverage(int pin)
{
  long sum = 0;

  for (int i = 0; i < 3; i++)
  {
    sum += analogRead(pin);
  }

  return sum / 3;
}

// =====================================================
// HIEN THI KET QUA AI
// =====================================================

void displayAIResult(const char* label, float confidence)
{
  if (strcmp(label, "NONE") == 0)
  {
    showLCD("DANG CHO CU CHI", "AI: NONE");
    return;
  }
  char visibleLabel[17];
  char confidenceText[17];
  snprintf(visibleLabel, sizeof(visibleLabel), "%.16s", label);
  for (size_t i = 0; visibleLabel[i] != '\0'; ++i)
  {
    if (visibleLabel[i] == '_') visibleLabel[i] = ' ';
  }
  snprintf(confidenceText, sizeof(confidenceText), "TC:%.1f%%", confidence);
  showLCD(visibleLabel, confidenceText);
}

void resetCommandBuffer()
{
  receiveLength = 0;
  receiveBuffer[0] = '\0';
  discardCommand = false;
}

void disconnectPython()
{
  pythonClient.stop();
  clientConnected = false;
  recordingActive = false;
  rawProtocolV2 = false;
  rawProtocolV5 = false;
  sampleInterval = 40;
  aiFresh = false;
  resetCommandBuffer();
  sequenceResultLatched = false;
  continuousMode = false;
}

bool writePacket(const char* packet, size_t length)
{
  if (!pythonClient.connected() ||
      pythonClient.write(reinterpret_cast<const uint8_t*>(packet), length) != length)
  {
    // A partial line must not be followed by another packet on the same stream.
    disconnectPython();
    showLCD("WIFI SAN SANG", "CHO PYTHON...");
    return false;
  }
  return true;
}

// =====================================================
// XU LY LENH PYTHON
// =====================================================

void processPythonCommand(char* line)
{
  if (strcmp(line, "RAW5_100") == 0)
  {
    rawProtocolV5 = true;
    rawProtocolV2 = false;
    sampleInterval = 10;
    lastSampleTime = millis();
    return;
  }
  // Default DATA5 includes all five fingers. RAW5 omits derivatives.
  if (strcmp(line, "RAW5") == 0)
  {
    sampleInterval = 40;
    lastSampleTime = millis();
    rawProtocolV5 = true;
    rawProtocolV2 = false;
    return;
  }
  // Compatibility for two-channel collectors: only flex1 and flex2 are sent.
  if (strcmp(line, "RAW2") == 0)
  {
    sampleInterval = 40;
    lastSampleTime = millis();
    rawProtocolV2 = true;
    rawProtocolV5 = false;
    return;
  }
  // Runtime mode shares this sketch with collection. Heartbeat detects a stalled
  // Python process even when TCP itself remains connected.
  if (strncmp(line, "RUN,", 4) == 0)
  {
    const char* state = line + 4;
    if (strcmp(state, "PING") == 0)
    {
      if (continuousMode) lastRunPacket = millis();
      return;
    }
    const char* first = nullptr;
    const char* second = nullptr;
    if (strcmp(state, "CALIBRATING") == 0) { first = "DANG LAY MOC MPU"; second = "DUOI TAY GIU YEN"; }
    else if (strcmp(state, "READY") == 0) { first = "SAN SANG"; second = "HAY LAM CU CHI"; }
    else if (strcmp(state, "TRACKING") == 0) { first = "DANG NHAN DIEN"; second = "LAM TRON CHUOI"; }
    else if (strcmp(state, "REST") == 0) { first = "CHO TAY NGHI"; second = "DUOI VA GIU YEN"; }
    else if (strcmp(state, "ERROR") == 0) { first = "DU LIEU GIAN DOAN"; second = "CHO NOI LAI"; }
    else if (strcmp(state, "OFF") == 0) { first = "DA DUNG AI"; second = "CHO PYTHON..."; }
    if (first == nullptr) return;
    continuousMode = strcmp(state, "OFF") != 0;
    lastRunPacket = millis();
    recordingActive = false;
    aiFresh = false;
    sequenceResultLatched = false;
    showLCD(first, second);
    return;
  }
  // Recording markers bound trials; sensor streaming continues in both modes.
  // time_ms remains elapsed time since boot. Python stores trial-relative time.
  if (strcmp(line, "START") == 0)
  {
    if (writePacket("BEGIN\n", 6))
    {
      recordingActive = true;
      continuousMode = false;
      aiFresh = false;
      sequenceResultLatched = false;
      showLCD("DANG THU DATA", "LAM CU CHI...");
    }
    return;
  }
  if (strcmp(line, "STOP") == 0)
  {
    if (writePacket("END\n", 4))
    {
      recordingActive = false;
      showLCD("PYTHON DA NOI", "DANG CHO AI...");
    }
    return;
  }
  // Manual whole-sequence result: no fabricated confidence for the SVM.
  // Keep the LAST completed result until START, disconnect, or another result.
  if (strncmp(line, "SEQ,", 4) == 0)
  {
    const char* label = line + 4;
    const char* message = nullptr;
    if (strcmp(label, "XIN_CHAO") == 0) message = "XIN CHAO";
    else if (strcmp(label, "CAM_ON") == 0) message = "CAM ON";
    else if (strcmp(label, "TAM_BIET") == 0) message = "TAM BIET";
    else if (strcmp(label, "NONE") == 0) message = "CHUA NHAN DIEN";
    if (message == nullptr || recordingActive) return;
    aiFresh = false;
    sequenceResultLatched = true;
    lastRunPacket = millis();
    showLCD(message, continuousMode ? "DUOI DE TIEP" : "KET QUA CUOI");
    return;
  }
  // AI,label,confidencePercent\n; labels use ASCII letters, digits, underscores.
  if (strncmp(line, "AI,", 3) != 0) return;
  char* label = line + 3;
  char* separator = strchr(label, ',');
  if (separator == nullptr || separator == label || separator - label > 48) return;
  *separator = '\0';
  for (const char* p = label; *p != '\0'; ++p)
  {
    if (!((*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9') || *p == '_')) return;
  }
  char* end = nullptr;
  const char* value = separator + 1;
  float confidence = strtof(value, &end);
  if (end == value || *end != '\0' || !isfinite(confidence) ||
      confidence < 0.0f || confidence > 100.0f) return;

  lastAIResult = millis();
  sequenceResultLatched = false;
  aiFresh = true;
  if (!recordingActive) displayAIResult(label, confidence);
}

// =====================================================
// DOC DU LIEU PYTHON GUI VE
// =====================================================

void readPython()
{
  // Bound work per loop so a command burst cannot starve 25 Hz sampling.
  size_t readBudget = 128;
  while (readBudget-- > 0 && pythonClient.connected() && pythonClient.available())
  {
    char c = pythonClient.read();
    if (c == '\n')
    {
      if (!discardCommand && receiveLength > 0)
      {
        receiveBuffer[receiveLength] = '\0';
        processPythonCommand(receiveBuffer);
      }
      resetCommandBuffer();
    }
    else if (c != '\r' && !discardCommand)
    {
      if (c == '\0' || receiveLength >= sizeof(receiveBuffer) - 1)
      {
        discardCommand = true;
      }
      else
      {
        receiveBuffer[receiveLength++] = c;
      }
    }
  }
}

// =====================================================
// GUI 1 MAU SENSOR QUA WIFI
// =====================================================

void sendSensorSample()
{
  // Timestamp acquisition, before sensor reads/formatting/network transmission.
  unsigned long elapsed = millis() - startTime;
  // ----------------------------
  // FLEX
  // ----------------------------

  int flex[FLEX_COUNT];
  float dFlex[FLEX_COUNT];
  float dFlexAvg[FLEX_COUNT];
  for (size_t finger = 0; finger < FLEX_COUNT; ++finger)
  {
    flex[finger] = readFlexAverage(FLEX_PINS[finger]);
    dFlex[finger] = flex[finger] - prevFlex[finger];
    prevFlex[finger] = flex[finger];
    dFlexHistory[finger][historyIndex] = dFlex[finger];
    dFlexAvg[finger] = (dFlexHistory[finger][0] +
                       dFlexHistory[finger][1] +
                       dFlexHistory[finger][2]) / 3.0f;
  }
  historyIndex = (historyIndex + 1) % 3;

  sensors_event_t a;
  sensors_event_t g;
  sensors_event_t temp;

  mpu.getEvent(
    &a,
    &g,
    &temp
  );

  // DATA5: time, five ADCs, five differences, five averaged differences, MPU.
  // RAW5: time, five ADCs, MPU. RAW2 is a legacy two-channel subset.
  char packet[384];
  int length;
  if (rawProtocolV5)
  {
    length = snprintf(packet, sizeof(packet),
      "%s,%lu,%d,%d,%d,%d,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
      sampleInterval == 10 ? "RAW5_100" : "RAW5",
      elapsed, flex[0], flex[1], flex[2], flex[3], flex[4],
      a.acceleration.x, a.acceleration.y, a.acceleration.z,
      g.gyro.x, g.gyro.y, g.gyro.z);
  }
  else if (rawProtocolV2)
  {
    length = snprintf(packet, sizeof(packet),
      "RAW2,%lu,%d,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
      elapsed, flex[0], flex[1],
      a.acceleration.x, a.acceleration.y, a.acceleration.z,
      g.gyro.x, g.gyro.y, g.gyro.z);
  }
  else
  {
    length = snprintf(packet, sizeof(packet),
      "DATA5,%lu,%d,%d,%d,%d,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.3f,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
      elapsed, flex[0], flex[1], flex[2], flex[3], flex[4],
      dFlex[0], dFlex[1], dFlex[2], dFlex[3], dFlex[4],
      dFlexAvg[0], dFlexAvg[1], dFlexAvg[2], dFlexAvg[3], dFlexAvg[4],
      a.acceleration.x, a.acceleration.y, a.acceleration.z,
      g.gyro.x, g.gyro.y, g.gyro.z);
  }
  if (length > 0 && static_cast<size_t>(length) < sizeof(packet))
  {
    writePacket(packet, static_cast<size_t>(length));
  }
  if (DEBUG_SENSOR)
  {
    for (size_t finger = 0; finger < FLEX_COUNT; ++finger)
    {
      Serial.print("F");
      Serial.print(finger + 1);
      Serial.print("=");
      Serial.print(flex[finger]);
      Serial.print(" ");
    }
    Serial.println();
  }
}

// =====================================================
// KET NOI WIFI
// =====================================================

void connectWiFi()
{
  WiFi.mode(WIFI_STA);

  // giảm delay WiFi
  WiFi.setSleep(false);

  WiFi.config(
    LOCAL_IP,
    GATEWAY,
    SUBNET
  );

  // Connection attempts and backoff are handled by serviceWiFi() in loop().
  showLCD("DANG NOI WIFI", "VUI LONG CHO...");
}

bool serviceWiFi()
{
  if (WiFi.status() == WL_CONNECTED)
  {
    if (!wifiOnline)
    {
      wifiOnline = true;
      wifiRetryInterval = 10000;
      wifiAttemptStarted = false;
      server.begin();
      server.setNoDelay(true);
      Serial.print("ESP32 IP: ");
      Serial.println(WiFi.localIP());
      Serial.println("TCP SERVER READY: 5000");
      showLCD("WIFI SAN SANG", "CHO PYTHON...");
    }
    return true;
  }

  if (wifiOnline)
  {
    disconnectPython();
    server.end();
    wifiOnline = false;
    wifiAttemptStarted = false;
    showLCD("MAT WIFI", "DANG NOI LAI...");
  }
  unsigned long now = millis();
  if (!wifiAttemptStarted || now - lastWiFiAttempt >= wifiRetryInterval)
  {
    if (wifiAttemptStarted)
    {
      WiFi.disconnect();
      wifiRetryInterval *= 2;
      if (wifiRetryInterval > MAX_WIFI_RETRY_INTERVAL)
        wifiRetryInterval = MAX_WIFI_RETRY_INTERVAL;
    }
    lastWiFiAttempt = now;
    wifiAttemptStarted = true;
    WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
    Serial.println("Dang ket noi WiFi...");
  }
  return false;
}

void resetFlexHistory()
{
  for (size_t finger = 0; finger < FLEX_COUNT; ++finger)
  {
    prevFlex[finger] = readFlexAverage(FLEX_PINS[finger]);
    for (int i = 0; i < 3; ++i) dFlexHistory[finger][i] = 0;
  }
  historyIndex = 0;
}

// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);

  delay(1200);

  Serial.println();
  Serial.println("==========================");
  Serial.println("SMART GLOVE WIFI AI");
  Serial.println("==========================");

  // =================================================
  // FLEX
  // =================================================

  analogReadResolution(12);

  for (size_t finger = 0; finger < FLEX_COUNT; ++finger)
  {
    pinMode(FLEX_PINS[finger], INPUT);
    analogSetPinAttenuation(FLEX_PINS[finger], ADC_11db);
  }

  // =================================================
  // LCD
  // =================================================

  Wire.begin(
    LCD_SDA,
    LCD_SCL
  );

  lcd.init();
  lcd.backlight();

  showLCD(
    "SMART GLOVE AI",
    "KHOI DONG..."
  );

  // =================================================
  // MPU6050
  // =================================================

  MPUWire.begin(
    MPU_SDA,
    MPU_SCL,
    400000
  );

  if (!mpu.begin(
        0x68,
        &MPUWire))
  {
    Serial.println(
      "LOI MPU6050"
    );

    showLCD(
      "LOI MPU6050",
      "KIEM TRA DAY"
    );

    while (true)
    {
      delay(1000);
    }
  }

  mpu.setAccelerometerRange(
    MPU6050_RANGE_2_G
  );

  mpu.setGyroRange(
    MPU6050_RANGE_250_DEG
  );

  mpu.setFilterBandwidth(
    MPU6050_BAND_21_HZ
  );
  // DLPF enabled: 1 kHz / (1 + 9) = 100 Hz MPU register updates.
  mpu.setSampleRateDivisor(9);

  Serial.println("MPU6050 OK");

  // =================================================
  // FLEX BAN DAU
  // =================================================

  resetFlexHistory();

  // =================================================
  // WIFI
  // =================================================

  connectWiFi();

  startTime = millis();
}

// =====================================================
// LOOP
// =====================================================

void loop()
{
  if (!serviceWiFi()) return;

  // =================================================
  // PYTHON CHUA KET NOI
  // =================================================

  if (
    !pythonClient ||
    !pythonClient.connected()
  )
  {
    if (clientConnected)
    {
      disconnectPython();
      showLCD("WIFI SAN SANG", "CHO PYTHON...");
    }
    WiFiClient newClient =
        server.available();

    if (newClient)
    {
      pythonClient = newClient;
      pythonClient.setNoDelay(true);
      clientConnected = true;
      aiFresh = false;
      recordingActive = false;
      resetCommandBuffer();
      resetFlexHistory();
      lastSampleTime = millis();
      Serial.println("PYTHON DA KET NOI!");
      showLCD("PYTHON DA NOI", "DANG CHO AI...");
    }
    else
    {
      return;
    }
  }

  // =================================================
  // NHAN KET QUA AI
  // =================================================

  readPython();
  if (!clientConnected) return;

  // =================================================
  // GUI SENSOR 25 Hz / 100 Hz theo giao thuc da chon
  // =================================================

  unsigned long now =
      millis();

  if (continuousMode && now - lastRunPacket > 6000)
  {
    continuousMode = false;
    sequenceResultLatched = false;
    aiFresh = false;
    showLCD("MAT TIN HIEU AI", "CHO PYTHON...");
  }

  // Python sends a fresh accepted prediction (or NONE) at least once a second.
  if (!sequenceResultLatched && aiFresh && now - lastAIResult > AI_TIMEOUT)
  {
    aiFresh = false;
    if (!recordingActive) showLCD("PYTHON DA NOI", "DANG CHO AI...");
  }

  if (
    now - lastSampleTime
    >= sampleInterval
  )
  {
    // Fixed deadlines avoid accumulating ordinary loop jitter. If a whole
    // period was missed, skip it; never invent catch-up samples/timestamps.
    lastSampleTime += sampleInterval;
    if (now - lastSampleTime >= sampleInterval) lastSampleTime = now;

    sendSensorSample();
  }
}

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

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

// Dataset/model hiện tại dùng 25 Hz
// 40 ms / mẫu
const unsigned long SAMPLE_INTERVAL = 40;

unsigned long lastSampleTime = 0;
unsigned long startTime = 0;

// =====================================================
// FLEX
// =====================================================

int prevFlex1 = 0;
int prevFlex2 = 0;

float dFlex1History[3] = {0, 0, 0};
float dFlex2History[3] = {0, 0, 0};

int historyIndex = 0;

// =====================================================
// NHAN LENH PYTHON
// =====================================================

String receiveBuffer = "";

// =====================================================
// LCD
// =====================================================

void showLCD(String line1, String line2)
{
  lcd.clear();

  if (line1.length() > 16)
    line1 = line1.substring(0, 16);

  if (line2.length() > 16)
    line2 = line2.substring(0, 16);

  lcd.setCursor(0, 0);
  lcd.print(line1);

  lcd.setCursor(0, 1);
  lcd.print(line2);
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

void displayAIResult(String label, float confidence)
{
  if (label == "XIN_CHAO")
  {
    showLCD(
      "XIN CHAO",
      "TC:" + String(confidence, 1) + "%"
    );
  }

  else if (label == "CAM_ON_NHIEU")
  {
    showLCD(
      "CAM ON NHIEU",
      "TC:" + String(confidence, 1) + "%"
    );
  }

  else
  {
    showLCD(
      "DANG CHO CU CHI",
      "AI: NONE"
    );
  }
}

// =====================================================
// XU LY LENH PYTHON
// =====================================================

void processPythonCommand(String line)
{
  line.trim();

  // Format:
  // AI,XIN_CHAO,96.52

  if (!line.startsWith("AI,"))
  {
    return;
  }

  int comma1 = line.indexOf(',');
  int comma2 = line.indexOf(',', comma1 + 1);

  if (comma1 < 0 || comma2 < 0)
  {
    return;
  }

  String label =
      line.substring(comma1 + 1, comma2);

  float confidence =
      line.substring(comma2 + 1).toFloat();

  Serial.println();
  Serial.println("======================");

  Serial.print("AI: ");
  Serial.println(label);

  Serial.print("TIN CAY: ");
  Serial.print(confidence, 2);
  Serial.println("%");

  Serial.println("======================");

  displayAIResult(
    label,
    confidence
  );
}

// =====================================================
// DOC DU LIEU PYTHON GUI VE
// =====================================================

void readPython()
{
  while (
    pythonClient &&
    pythonClient.connected() &&
    pythonClient.available()
  )
  {
    char c = pythonClient.read();

    if (c == '\n')
    {
      processPythonCommand(
        receiveBuffer
      );

      receiveBuffer = "";
    }

    else if (c != '\r')
    {
      receiveBuffer += c;

      if (receiveBuffer.length() > 100)
      {
        receiveBuffer = "";
      }
    }
  }
}

// =====================================================
// GUI 1 MAU SENSOR QUA WIFI
// =====================================================

void sendSensorSample()
{
  // ----------------------------
  // FLEX
  // ----------------------------

  int flex1 =
      readFlexAverage(FLEX1_PIN);

  int flex2 =
      readFlexAverage(FLEX2_PIN);

  float dFlex1 =
      flex1 - prevFlex1;

  float dFlex2 =
      flex2 - prevFlex2;

  prevFlex1 = flex1;
  prevFlex2 = flex2;

  // ----------------------------
  // MOVING AVERAGE dFlex 3 MAU
  // ----------------------------

  dFlex1History[historyIndex] =
      dFlex1;

  dFlex2History[historyIndex] =
      dFlex2;

  historyIndex++;

  if (historyIndex >= 3)
  {
    historyIndex = 0;
  }

  float dFlex1Avg =
      (
        dFlex1History[0] +
        dFlex1History[1] +
        dFlex1History[2]
      ) / 3.0;

  float dFlex2Avg =
      (
        dFlex2History[0] +
        dFlex2History[1] +
        dFlex2History[2]
      ) / 3.0;

  // ----------------------------
  // MPU6050
  // ----------------------------

  sensors_event_t a;
  sensors_event_t g;
  sensors_event_t temp;

  mpu.getEvent(
    &a,
    &g,
    &temp
  );

  unsigned long elapsed =
      millis() - startTime;

  // =================================================
  // GUI THEO DUNG DINH DANG DATASET CU
  //
  // DATA,
  // time_ms,
  // flex1,flex2,
  // dFlex1,dFlex2,
  // dFlex1Avg,dFlex2Avg,
  // ax,ay,az,
  // gx,gy,gz
  // =================================================

  pythonClient.print("DATA,");

  pythonClient.print(elapsed);
  pythonClient.print(",");

  pythonClient.print(flex1);
  pythonClient.print(",");

  pythonClient.print(flex2);
  pythonClient.print(",");

  pythonClient.print(dFlex1, 3);
  pythonClient.print(",");

  pythonClient.print(dFlex2, 3);
  pythonClient.print(",");

  pythonClient.print(dFlex1Avg, 3);
  pythonClient.print(",");

  pythonClient.print(dFlex2Avg, 3);
  pythonClient.print(",");

  pythonClient.print(
    a.acceleration.x, 6
  );
  pythonClient.print(",");

  pythonClient.print(
    a.acceleration.y, 6
  );
  pythonClient.print(",");

  pythonClient.print(
    a.acceleration.z, 6
  );
  pythonClient.print(",");

  pythonClient.print(
    g.gyro.x, 6
  );
  pythonClient.print(",");

  pythonClient.print(
    g.gyro.y, 6
  );
  pythonClient.print(",");

  pythonClient.print(
    g.gyro.z, 6
  );

  pythonClient.print("\n");

  // Debug
  Serial.print("F1=");
  Serial.print(flex1);

  Serial.print(" F2=");
  Serial.println(flex2);
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

  WiFi.begin(
    WIFI_NAME,
    WIFI_PASSWORD
  );

  Serial.print(
    "Dang ket noi WiFi"
  );

  while (
    WiFi.status() != WL_CONNECTED
  )
  {
    Serial.print(".");
    delay(500);
  }

  Serial.println();
  Serial.println("WIFI OK");

  Serial.print("ESP32 IP: ");
  Serial.println(
    WiFi.localIP()
  );
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

  pinMode(FLEX1_PIN, INPUT);
  pinMode(FLEX2_PIN, INPUT);

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
    MPU6050_RANGE_8_G
  );

  mpu.setGyroRange(
    MPU6050_RANGE_500_DEG
  );

  mpu.setFilterBandwidth(
    MPU6050_BAND_21_HZ
  );

  Serial.println("MPU6050 OK");

  // =================================================
  // FLEX BAN DAU
  // =================================================

  prevFlex1 =
      readFlexAverage(FLEX1_PIN);

  prevFlex2 =
      readFlexAverage(FLEX2_PIN);

  // =================================================
  // WIFI
  // =================================================

  connectWiFi();

  // =================================================
  // TCP SERVER
  // =================================================

  server.begin();
  server.setNoDelay(true);

  Serial.println();
  Serial.println(
    "TCP SERVER READY"
  );

  Serial.print("PORT: ");
  Serial.println(SERVER_PORT);

  showLCD(
    "WIFI SAN SANG",
    "CHO PYTHON..."
  );

  startTime = millis();
}

// =====================================================
// LOOP
// =====================================================

void loop()
{
  // =================================================
  // WIFI MAT
  // =================================================

  if (
    WiFi.status() != WL_CONNECTED
  )
  {
    showLCD(
      "MAT WIFI",
      "DANG NOI LAI..."
    );

    if (pythonClient)
    {
      pythonClient.stop();
    }

    connectWiFi();

    server.begin();
  }

  // =================================================
  // PYTHON CHUA KET NOI
  // =================================================

  if (
    !pythonClient ||
    !pythonClient.connected()
  )
  {
    WiFiClient newClient =
        server.available();

    if (newClient)
    {
      pythonClient = newClient;

      pythonClient.setNoDelay(true);

      Serial.println();
      Serial.println(
        "PYTHON DA KET NOI!"
      );

      showLCD(
        "PYTHON DA NOI",
        "AI SAN SANG"
      );

      // reset dFlex
      prevFlex1 =
          readFlexAverage(FLEX1_PIN);

      prevFlex2 =
          readFlexAverage(FLEX2_PIN);

      for (int i = 0; i < 3; i++)
      {
        dFlex1History[i] = 0;
        dFlex2History[i] = 0;
      }

      historyIndex = 0;

      lastSampleTime =
          millis();
    }
    else
    {
      delay(5);
      return;
    }
  }

  // =================================================
  // NHAN KET QUA AI
  // =================================================

  readPython();

  // =================================================
  // GUI SENSOR 25 Hz
  // =================================================

  unsigned long now =
      millis();

  if (
    now - lastSampleTime
    >= SAMPLE_INTERVAL
  )
  {
    lastSampleTime = now;

    sendSensorSample();
  }
}
// ESP32: test ONLY flex 4 (ring finger), GPIO 35.
// Wiring: 3.3V -> flex -> GPIO35 junction -> 10k resistor -> GND.
// Serial Monitor: 115200 baud. No MPU, LCD, Wi-Fi, model or calibration.
#include <Arduino.h>

const int FLEX_PIN = 35;
const uint32_t SAMPLE_US = 10000;  // nominal 100 Hz
uint32_t nextSample;
uint32_t reportStarted;
uint32_t lastDisplay;
int previousADC = -1;
int lowADC = 4095, highADC = 0;
int rawLow = 4095, rawHigh = 0;
int largestJump = 0;
unsigned int samples = 0, jumps = 0, rails = 0;
uint32_t sumADC = 0, maxGapUs = 0, previousSampleUs = 0;

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(FLEX_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(FLEX_PIN, ADC_11db);
  Serial.println("\nTEST FLEX 4 - AP UT - GPIO35 - 115200 BAUD");
  Serial.println("3.3V -> FLEX -> GPIO35 -> 10k -> GND");
  Serial.println("ADC = trung binh 3 lan doc, giong firmware chinh; khong loc median.");
  Serial.println("MOI 1s: min/max, buoc nhay lon nhat, so lan nhay >400 ADC, so mau sat bien.");
  Serial.println("1. DUOI GIU YEN 10s. 2. GAP GIU YEN 10s. 3. GAP/DUOI CHAM 5 LAN.");
  reportStarted = lastDisplay = millis();
  nextSample = micros();
}

void loop() {
  const uint32_t nowUs = micros();
  if (static_cast<int32_t>(nowUs - nextSample) < 0) return;
  nextSample += SAMPLE_US;
  // Do not invent catch-up samples after an unexpected delay.
  if (static_cast<int32_t>(nowUs - nextSample) >= 0)
    nextSample = nowUs + SAMPLE_US;
  if (previousSampleUs != 0) {
    const uint32_t gap = nowUs - previousSampleUs;
    if (gap > maxGapUs) maxGapUs = gap;
  }
  previousSampleUs = nowUs;

  int total = 0;
  bool atRail = false;
  for (int i = 0; i < 3; ++i) {
    const int raw = analogRead(FLEX_PIN);
    total += raw;
    if (raw < rawLow) rawLow = raw;
    if (raw > rawHigh) rawHigh = raw;
    if (raw <= 8 || raw >= 4087) atRail = true;
  }
  const int adc = total / 3;
  const int step = previousADC < 0 ? 0 : abs(adc - previousADC);
  previousADC = adc;
  if (adc < lowADC) lowADC = adc;
  if (adc > highADC) highADC = adc;
  if (step > largestJump) largestJump = step;
  if (step > 400) ++jumps;
  if (atRail) ++rails;
  sumADC += adc;
  ++samples;

  const uint32_t nowMs = millis();
  if (nowMs - lastDisplay >= 200) {
    lastDisplay = nowMs;
    Serial.printf("F4=%d | buoc=%d | min/max=%d/%d\n", adc, step, lowADC, highADC);
  }
  if (nowMs - reportStarted >= 1000) {
    Serial.printf("TONG KET F4: TB=%.1f | min/max=%d/%d | raw=%d..%d | "
                  "nhay_max=%d | nhay>400=%u | sat_bien=%u/%u | gap_max=%lu us\n",
                  float(sumADC) / samples, lowADC, highADC, rawLow, rawHigh,
                  largestJump, jumps, rails, samples, static_cast<unsigned long>(maxGapUs));
    reportStarted = nowMs;
    lowADC = rawLow = 4095;
    highADC = rawHigh = largestJump = 0;
    samples = jumps = rails = 0;
    sumADC = maxGapUs = 0;
  }
}

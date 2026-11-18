// Standalone ESP32-S3 N16R8, 14 words + NONE, no Python at runtime.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Preferences.h>
#include "esp_heap_caps.h"
#include "config.h"
#include "features.h"
#include "model.h"
#include "sentence.h"

#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error Select ESP32S3 Dev Module, not ESP32 Dev Module
#endif

using GloveFeatures::Sample;
using GloveFeatures::Calibration;
Adafruit_MPU6050 mpu;
Preferences preferences;
Calibration calibration{};
GloveFeatures::Imu imu;
constexpr int RING_SIZE=200;
Sample ring[RING_SIZE], snapshot[150];
float features[2850];
double gridWorkspace[150][14], flexWorkspace[150][5];
portMUX_TYPE ringMux=portMUX_INITIALIZER_UNLOCKED;
int ringHead=0, ringCount=0;
uint32_t serialSample=0, generation=0;
int pendingError=0; // 1..5 flex rails, 6 MPU read, 7 timing, 8 MPU clipping.
int pendingSpike=0;
bool sentences=false, showFlex=false;
Sentence sentence;
int lastCandidate=-1, streak=0;

bool readSensors(Sample& s) {
  s.stamp=millis();
  for (int k=0;k<5;++k) {
    int sum=0; for (int j=0;j<3;++j) sum+=analogRead(FLEX_PINS[k]);
    s.flex[k]=sum/3; // Same integer average as the original ESP32 firmware.
  }
  sensors_event_t a,g,temp;
  if (!mpu.getEvent(&a,&g,&temp)) return false;
  s.acc[0]=a.acceleration.x; s.acc[1]=a.acceleration.y; s.acc[2]=a.acceleration.z;
  s.gyro[0]=g.gyro.x; s.gyro[1]=g.gyro.y; s.gyro[2]=g.gyro.z;
  return true;
}

bool waitEnter() {
  // Allow Enter or any non-newline key, then consume trailing CR/LF later.
  while (!Serial.available()) delay(10);
  while (Serial.available()) Serial.read();
  return true;
}

// 1 second settling + 2 seconds measured; no synthetic catch-up samples.
bool pose(Sample* out) {
  for (int n=5;n>0;--n) { Serial.println(n); delay(1000); }
  Serial.println("GIU YEN 3 GIAY...");
  uint32_t next=millis(),previous=0;
  for (int i=0;i<300;++i) {
    while (int32_t(millis()-next)<0) delay(1);
    Sample s{};
    if (!readSensors(s)) { Serial.println("LOI MPU: kiem tra SDA=11 SCL=12, nguon va GND."); return false; }
    if (previous && (s.stamp<=previous || s.stamp-previous>20)) {
      Serial.println("LOI: mat nhip cam bien khi hieu chuan; thu lai."); return false;
    }
    previous=s.stamp; next=s.stamp+10;
    for (int k=0;k<5;++k) if (s.flex[k]<=8 || s.flex[k]>=4087) {
      Serial.printf("LOI F%d GPIO%d: ADC=%.0f; sua day roi thu lai.\n",k+1,FLEX_PINS[k],s.flex[k]); return false;
    }
    if (i>=100) out[i-100]=s;
  }
  return true;
}

bool calibrateFlex() {
  // Reuse ring as temporary calibration storage before acquisition task starts.
  static double opened[5][200], closed[5][200], work[200];
  while (true) {
    Serial.println("DUOI CA 5 NGON, Enter de dem nguoc va do."); waitEnter();
    if (!pose(ring)) continue;
    for (int k=0;k<5;++k) for (int i=0;i<200;++i) opened[k][i]=ring[i].flex[k];
    Serial.println("GAP CA 5 NGON vua phai (ca khop ngon cai), Enter de do."); waitEnter();
    if (!pose(ring)) continue;
    for (int k=0;k<5;++k) for (int i=0;i<200;++i) closed[k][i]=ring[i].flex[k];
    bool good=true;
    for (int k=0;k<5;++k) {
      double drift[2],lo[2],hi[2],med[2];
      for (int mode=0;mode<2;++mode) {
        const double* values=mode?closed[k]:opened[k];
        memcpy(work,values,50*sizeof(double)); double first=GloveFeatures::median(work,50);
        memcpy(work,values+150,50*sizeof(double)); double last=GloveFeatures::median(work,50);
        drift[mode]=fabs(last-first);
        memcpy(work,values,200*sizeof(double)); med[mode]=GloveFeatures::median(work,200);
        lo[mode]=work[9]*.05+work[10]*.95;
        hi[mode]=work[189]*.95+work[190]*.05;
      }
      double span=med[0]-med[1], separation=lo[0]-hi[1];
      bool ok=span>=15 && separation>=5 && fmax(drift[0],drift[1])<=fmax(5,.2*span);
      Serial.printf("%s F%d/GPIO%d: duoi=%.1f gap=%.1f span=%.1f tach=%.1f drift=%.1f\n",
        ok?"DAT":"CHUA DAT",k+1,FLEX_PINS[k],med[0],med[1],span,separation,fmax(drift[0],drift[1]));
      calibration.opened[k]=med[0]; calibration.closed[k]=med[1]; good&=ok;
    }
    if (!good) { Serial.println("Flex chua dat. Chinh day/giu yen roi do lai."); continue; }
    preferences.putBytes("open",calibration.opened,sizeof(calibration.opened));
    preferences.putBytes("closed",calibration.closed,sizeof(calibration.closed));
    preferences.putUInt("schema",1);
    return true;
  }
}

void calibrateMpu() {
  static double work[200];
  while (true) {
    Serial.println("DAT TAY YEN: tu dong lay moc MPU. Khong can bam Enter.");
    if (!pose(ring)) { delay(500); continue; }
    double accStd=0,gyroStd=0;
    for (int k=0;k<3;++k) {
      double a=0,g=0,a2=0,g2=0;
      for (int i=0;i<200;++i) { double av=ring[i].acc[k],gv=ring[i].gyro[k]; a+=av;g+=gv;a2+=av*av;g2+=gv*gv;work[i]=gv; }
      accStd=fmax(accStd,sqrt(fmax(0,a2/200-(a/200)*(a/200))));
      gyroStd=fmax(gyroStd,sqrt(fmax(0,g2/200-(g/200)*(g/200))));
      calibration.bias[k]=GloveFeatures::median(work,200);
    }
    for (int i=0;i<200;++i) work[i]=sqrt(ring[i].acc[0]*ring[i].acc[0]+ring[i].acc[1]*ring[i].acc[1]+ring[i].acc[2]*ring[i].acc[2]);
    calibration.gravity=GloveFeatures::median(work,200);
    if (gyroStd>.03 || accStd>.3 || calibration.gravity<7 || calibration.gravity>12) {
      Serial.printf("CANH BAO MPU chua yen/hop le: acc_std=%.3f gyro_std=%.3f g=%.3f. Se do lai.\n",accStd,gyroStd,calibration.gravity);
      delay(1000); continue;
    }
    Serial.println("MPU DAT. Tiep tuc giu yen 2 giay khoi tao bo loc."); return;
  }
}

void invalidate(int error) {
  portENTER_CRITICAL(&ringMux);
  ringCount=0; ++generation; pendingError=error;
  portEXIT_CRITICAL(&ringMux);
}

void sampler(void*) {
  TickType_t next=xTaskGetTickCount();
  uint32_t previous=0; double lastFlex[5]{}; bool haveFlex=false;
  for (;;) {
    Sample s{};
    if (!readSensors(s)) { invalidate(6); imu.reset(); haveFlex=false; }
    else {
      bool good=true; int bad=0;
      if (previous && (s.stamp<=previous || s.stamp-previous>20)) { good=false;bad=7;imu.reset(); }
      previous=s.stamp;
      double steps[5];
      for (int k=0;k<5;++k) {
        steps[k]=fabs(s.flex[k]-lastFlex[k]); lastFlex[k]=s.flex[k];
        if (s.flex[k]<=8 || s.flex[k]>=4087) { good=false;bad=k+1; }
      }
      // Match current runtime policy: in-range jumps warn; median preprocessing
      // remains unchanged. Rails, clipping and missing samples discard windows.
      if (haveFlex) for (int k=0;k<5;++k) if (steps[k]>400) {
        bool isolated=true; for (int j=0;j<5;++j) if (j!=k && steps[j]>=50) isolated=false;
        if (isolated) { portENTER_CRITICAL(&ringMux);pendingSpike=k+1;portEXIT_CRITICAL(&ringMux); }
      }
      haveFlex=true;
      for (int k=0;k<3;++k) if (!isfinite(s.acc[k]) || !isfinite(s.gyro[k]) || fabs(s.acc[k])>=39 || fabs(s.gyro[k])>=17.36) { good=false;bad=8; }
      if (!good) invalidate(bad);
      if (bad==8) imu.reset();
      bool ready=bad!=8 && imu.process(s,calibration);
      if (good && ready) {
        portENTER_CRITICAL(&ringMux);
        ring[ringHead]=s; ringHead=(ringHead+1)%RING_SIZE;
        if (ringCount<RING_SIZE) ++ringCount;
        ++serialSample;
        portEXIT_CRITICAL(&ringMux);
      }
    }
    vTaskDelayUntil(&next,pdMS_TO_TICKS(SAMPLE_MS));
    // A late task starts a new schedule; never synthesize catch-up readings.
    if (int32_t(xTaskGetTickCount()-next)>0) next=xTaskGetTickCount();
  }
}

void printSentence() {
  if (!sentence.active) return;
  Serial.print("CUA SO: ");
  for (int i=0;i<sentence.size;++i) {
    if (i) Serial.print(", ");
    Serial.printf("%sx%d",GloveModel::LABELS[sentence.runs[i].label],sentence.runs[i].count);
  }
  Serial.println();
  int words[128],n=sentence.words(words);
  Serial.print("KET QUA CAU: ");
  if (!n) Serial.print("(chua nhan duoc tu nao)");
  else if (n==1 && words[0]==sentence.id("CHAO")) Serial.print("XIN CHAO");
  else if (n==2 && words[0]==sentence.id("TOI") && words[1]==sentence.id("TEN")) Serial.print("TOI TEN LA");
  else {
    for (int i=0;i<n;++i) { if (i) Serial.print(' '); Serial.print(GloveModel::LABELS[words[i]]); }
    if (n==2 && words[0]==sentence.id("BAN") && words[1]==sentence.id("KHOE")) Serial.print(" KHONG");
  }
  Serial.println(); sentence.reset();
}

void setup() {
  Serial.begin(115200);
  delay(2000); // Do not block standalone boot waiting for a USB host.
  Serial.println("\nSMART GLOVE ESP32-S3 N16R8 - 14 TU + NONE - NHAN DIEN TREN CHIP");
  Serial.printf("Flash=%u | PSRAM=%u | heap=%u bytes\n",ESP.getFlashChipSize(),ESP.getPsramSize(),ESP.getFreeHeap());
  Serial.printf("Model flash tables=%u bytes; khong chep model vao RAM.\n",unsigned(sizeof(GloveModel::NODES)+sizeof(GloveModel::ROOTS)));
  analogReadResolution(12);
  for (int k=0;k<5;++k) { pinMode(FLEX_PINS[k],INPUT);analogSetPinAttenuation(FLEX_PINS[k],ADC_11db); }
  Wire.begin(MPU_SDA,MPU_SCL,400000);Wire.setTimeOut(20);
  if (!mpu.begin(0x68,&Wire) && !mpu.begin(0x69,&Wire)) {
    Serial.println("DUNG: khong tim thay MPU6050. SDA=11, SCL=12; kiem tra nguon/GND/AD0. Reset sau khi sua.");
    while (true) delay(1000);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
  mpu.setGyroRange(MPU6050_RANGE_1000_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  mpu.setSampleRateDivisor(9);
  preferences.begin("glove-s3",false);
  bool stored=preferences.getUInt("schema",0)==1 &&
    preferences.getBytes("open",calibration.opened,sizeof(calibration.opened))==sizeof(calibration.opened) &&
    preferences.getBytes("closed",calibration.closed,sizeof(calibration.closed))==sizeof(calibration.closed);
  if (stored) for (int k=0;k<5;++k)
    if (!isfinite(calibration.opened[k]) || !isfinite(calibration.closed[k]) || calibration.opened[k]-calibration.closed[k]<15) stored=false;
  if (stored) Serial.println("Da nap moc FLEX luu tren chip. Go C sau khoi dong neu can hieu chuan lai.");
  else calibrateFlex();
  calibrateMpu();
  ringCount=ringHead=0;
  if (xTaskCreatePinnedToCore(sampler,"glove100Hz",8192,nullptr,3,nullptr,0)!=pdPASS) {
    Serial.println("DUNG: khong tao duoc task cam bien."); while (true) delay(1000);
  }
  Serial.println("LENH: W=test tu | S=ghep cau | F=bat/tat thong so flex | C=hieu chuan lai va reboot | Enter=chot cau.");
  Serial.println("MAC DINH TEST TU: cua so 1.5s, cap nhat 0.25s; cho khoi tao MPU va du mau.");
}

void loop() {
  static uint32_t used=0,seenGeneration=0,lastError=0,lastFlexDisplay=0;
  static int lastPrintedError=0;
  while (Serial.available()) {
    char c=Serial.read();
    if (c=='c' || c=='C') { preferences.clear();Serial.println("Xoa moc flex, khoi dong lai de hieu chuan.");delay(100);ESP.restart(); }
    if (c=='w' || c=='W' || c=='s' || c=='S') {
      sentences=c=='s' || c=='S'; sentence.reset(); lastCandidate=-1;streak=0;
      portENTER_CRITICAL(&ringMux);ringCount=0;++generation;portEXIT_CRITICAL(&ringMux);
      Serial.println(sentences?"GHEP CAU: ket thuc khi 10 NONE lien tiep. Enter chot thu cong.":"TEST TUNG TU LIEN TUC.");
    }
    if (c=='f' || c=='F') showFlex=!showFlex;
    if ((c=='\n' || c=='\r') && sentences) printSentence();
  }
  uint32_t count,gen; int error,spike; bool available=false;
  portENTER_CRITICAL(&ringMux);
  count=serialSample;gen=generation;error=pendingError;pendingError=0;spike=pendingSpike;pendingSpike=0;
  if (ringCount>=150 && count-used>=25) {
    for (int i=0;i<150;++i) snapshot[i]=ring[(ringHead-150+i+RING_SIZE)%RING_SIZE];
    available=true;
  }
  portEXIT_CRITICAL(&ringMux);
  if (gen!=seenGeneration) { seenGeneration=gen;sentence.reset();lastCandidate=-1;streak=0; }
  if (error && (error!=lastPrintedError || millis()-lastError>=1000)) {
    lastError=millis();lastPrintedError=error;
    if (error<=5) Serial.printf("LOI F%d GPIO%d: ADC sat bien; huy cua so/cau, kiem tra day.\n",error,FLEX_PINS[error-1]);
    else Serial.println(error==6?"LOI MPU: doc I2C that bai; huy cua so/cau.":error==7?"LOI NHiP: mat mau >20ms; lay lai huong MPU va cua so moi.":"LOI MPU: bao hoa/khong hop le; huy cua so/cau.");
  }
  if (spike && millis()-lastError>=1000) {
    lastError=millis();Serial.printf("CANH BAO F%d/GPIO%d nhay >400 ADC; can kiem tra day. Median model giu nguyen.\n",spike,FLEX_PINS[spike-1]);
  }
  if (!available) { delay(2);return; }
  used=count;
  if (!GloveFeatures::build(snapshot,calibration,features,gridWorkspace,flexWorkspace)) {
    sentence.reset();lastCandidate=-1;streak=0;
    if (millis()-lastError>1000) { Serial.println("LOI CUA SO: timestamp/flex khong hop le; bo cua so.");lastError=millis(); }
    return;
  }
  uint16_t votes[15]; uint32_t started=micros();
  int label=GloveModel::predict(features,votes);
  uint32_t elapsed=micros()-started;
  // A sensor fault while inference was running invalidates this result too.
  portENTER_CRITICAL(&ringMux);gen=generation;portEXIT_CRITICAL(&ringMux);
  if (gen!=seenGeneration) { sentence.reset();lastCandidate=-1;streak=0;return; }
  if (sentences) {
    int state=sentence.push(label);
    if (state<0) Serial.println("HUY CAU: qua 128 nhom nhan; hay chia cau ngan hon.");
    if (state==1) printSentence();
  } else {
    streak=lastCandidate==label?streak+1:1;lastCandidate=label;
    if (streak>=WORD_CONFIRMATIONS) Serial.printf("KET QUA: %s | %.2f Hz | model %.2f ms\n",GloveModel::LABELS[label],149000.0/(snapshot[149].stamp-snapshot[0].stamp),elapsed/1000.0);
    else Serial.printf("CHO XAC NHAN: %s\n",GloveModel::LABELS[label]);
  }
  if (showFlex && millis()-lastFlexDisplay>=1000) {
    lastFlexDisplay=millis(); Serial.print("FLEX (0=duoi,1=gap): ");
    for (int k=0;k<5;++k) Serial.printf("F%d=%.2f ADC=%.0f%s",k+1,flexWorkspace[149][k],snapshot[149].flex[k],k==4?"\n":" | ");
  }
}

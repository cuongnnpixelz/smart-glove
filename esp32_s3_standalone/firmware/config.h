#pragma once
#include <stdint.h>
// ESP32-S3-WROOM-1 N16R8 / DevKitC-style headers. See README before wiring.
// F1 thumb, F2 index, F3 middle, F4 ring, F5 little; ADC1 only.
constexpr uint8_t FLEX_PINS[5] = {4, 5, 6, 7, 8};
constexpr uint8_t MPU_SDA = 11, MPU_SCL = 12;
constexpr uint32_t SAMPLE_MS = 10, PREDICT_STEP_MS = 250;
constexpr int WORD_CONFIRMATIONS = 2, SENTENCE_MIN_VOTES = 5;
constexpr int NONE_END_WINDOWS = 10;
// Reserved for future LCD/audio support, not driven by this sketch:
// LCD SDA=15 SCL=16; MAX98357A BCLK=17 LRC=18 DIN=21.
// Leave GPIO19/20 free for native USB, GPIO35/36/37 for OPI PSRAM.

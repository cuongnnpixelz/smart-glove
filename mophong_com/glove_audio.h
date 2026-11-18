#pragma once
// Version 1: 16 kHz mono G.711 mu-law over USB; stereo 16-bit I2S to MAX98357A.
// Only the Arduino loop writes Serial. The audio task cannot interleave RAW lines.
#include <Arduino.h>
#include <atomic>
#include "driver/i2s.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

namespace GloveAudio {
constexpr size_t BLOCK_SIZE = 1024;
constexpr uint32_t RATE = 16000;
constexpr int BCLK = 18, LRC = 19, DIN = 23;
// Half-scale digital amplitude cap for the user's 4-ohm / 2 W speaker.
// User confirmed VIN=3.3 V and GAIN floating (nominal 9 dB).
// Previously /4; /2 doubles amplitude (+6.02 dB), not perceived loudness.
// This is NOT a calibrated watt limiter; do not increase hardware gain blindly.
constexpr int AMPLITUDE_DIVISOR = 2;
struct Block { uint32_t job, sequence; uint16_t size; uint8_t data[BLOCK_SIZE]; };
struct Result { uint32_t job; bool ok; };
static QueueHandle_t blocks = nullptr, results = nullptr;
static std::atomic<uint32_t> active{0};
static bool ready = false, receiving = false, pending = false, ending = false;
static Block input;
static size_t received = 0;
static uint32_t expectedCRC = 0, nextSequence = 0, lastInput = 0, totalBytes = 0;

static int16_t decode(uint8_t value) {
  value = ~value;
  int sample = (((value & 15) << 3) + 0x84) << ((value & 0x70) >> 4);
  sample -= 0x84;
  if (value & 0x80) sample = -sample;
  return static_cast<int16_t>(sample / AMPLITUDE_DIVISOR);
}

static uint32_t crc32(const uint8_t* bytes, size_t count) {
  uint32_t crc = 0xffffffff;
  for (size_t i = 0; i < count; ++i) {
    crc ^= bytes[i];
    for (int bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}

static bool writeSamples(const int16_t* pcm, size_t frames) {
  size_t written = 0;
  return i2s_write(I2S_NUM_0, pcm, frames * 4, &written, pdMS_TO_TICKS(1000)) == ESP_OK
         && written == frames * 4;
}

static void worker(void*) {
  Block block;
  int16_t pcm[256 * 2];
  while (true) {
    if (xQueueReceive(blocks, &block, pdMS_TO_TICKS(100)) != pdTRUE) continue;
    if (active.load() != block.job) continue;
    if (block.sequence == 0 && block.size) {
      // A small initial cushion absorbs USB scheduling jitter without holding
      // the sampling loop. Short clips start after at most 200 ms.
      const uint32_t began = millis();
      while (active.load() == block.job && uxQueueMessagesWaiting(blocks) < 2 &&
             millis() - began < 200)
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    bool ok = true;
    if (block.size) {
      for (size_t offset = 0; offset < block.size && active.load() == block.job; offset += 256) {
        const size_t count = min(size_t(256), size_t(block.size) - offset);
        for (size_t i = 0; i < count; ++i)
          pcm[2*i] = pcm[2*i+1] = decode(block.data[offset+i]);
        if (!writeSamples(pcm, count)) { ok = false; break; }
      }
    } else {
      // Flush the final speech samples through DMA before acknowledging DONE.
      memset(pcm, 0, sizeof(pcm));
      for (int i = 0; i < 4 && ok && active.load() == block.job; ++i)
        ok = writeSamples(pcm, 256);
      vTaskDelay(pdMS_TO_TICKS(40));
    }
    if (active.load() != block.job || !ok) i2s_zero_dma_buffer(I2S_NUM_0);
    if (active.load() == block.job && (!block.size || !ok)) {
      Result result{block.job, ok};
      xQueueSend(results, &result, pdMS_TO_TICKS(100));
    }
  }
}

static bool init() {
  if (ready) return true;
  i2s_config_t config = {};
  config.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = RATE;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.dma_buf_count = 4;
  config.dma_buf_len = 128;
  config.tx_desc_auto_clear = true;
  if (i2s_driver_install(I2S_NUM_0, &config, 0, nullptr) != ESP_OK) return false;
  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = BCLK;
  pins.ws_io_num = LRC;
  pins.data_out_num = DIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  if (i2s_set_pin(I2S_NUM_0, &pins) != ESP_OK) {
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }
  i2s_zero_dma_buffer(I2S_NUM_0);
  blocks = xQueueCreate(8, sizeof(Block));
  results = xQueueCreate(4, sizeof(Result));
  if (!blocks || !results ||
      xTaskCreatePinnedToCore(worker, "gloveAudio", 8192, nullptr, 1, nullptr, 0) != pdPASS) {
    if (blocks) vQueueDelete(blocks);
    if (results) vQueueDelete(results);
    blocks = results = nullptr;
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }
  ready = true;
  return true;
}

static void abort() {
  active.store(0);
  receiving = pending = ending = false;
  received = totalBytes = 0;
  if (blocks) xQueueReset(blocks);
}

static void fail(const char* reason, uint32_t job) {
  abort();
  Serial.printf("AUDIO_ERROR,%lu,%s\n", (unsigned long)job, reason);
}

static void service() {
  if (!ready) return;
  Result result;
  while (xQueueReceive(results, &result, 0) == pdTRUE) {
    if (result.job != active.load()) continue;
    if (result.ok) {
      active.store(0);
      ending = false;
      Serial.printf("AUDIO_DONE,%lu\n", (unsigned long)result.job);
    } else fail("I2S_WRITE", result.job);
  }
  if (pending && xQueueSend(blocks, &input, 0) == pdTRUE) {
    pending = false;
    if (input.size) {
      Serial.printf("AUDIO_ACK,%lu,%lu\n", (unsigned long)input.job, (unsigned long)input.sequence);
      ++nextSequence;
      totalBytes += input.size;
    }
  }
  if (active.load() && millis() - lastInput > 5000)
    fail("TIMEOUT", active.load());
}

static bool consume(uint8_t byte) {
  if (!receiving) return false;
  input.data[received++] = byte;
  lastInput = millis();
  if (received == input.size) {
    receiving = false;
    if (crc32(input.data, input.size) != expectedCRC) fail("CRC", input.job);
    else pending = true;
  }
  return true;
}

static bool command(const char* line) {
  if (strncmp(line, "AUDIO_", 6) != 0) return false;
  if (strcmp(line, "AUDIO_HELLO") == 0) {
    if (init()) Serial.println("AUDIO_READY,1,16000,1024");
    else Serial.println("AUDIO_ERROR,0,I2S_INIT");
    return true;
  }
  unsigned long job = 0, sequence = 0, size = 0, crc = 0;
  int used = 0;
  if (sscanf(line, "AUDIO_ABORT,%lu%n", &job, &used) == 1 && line[used] == '\0') {
    if (active.load() == job) abort();
    return true;
  }
  if (sscanf(line, "AUDIO_BEGIN,%lu%n", &job, &used) == 1 && line[used] == '\0') {
    if (!ready) { Serial.println("AUDIO_ERROR,0,NOT_READY"); return true; }
    if (active.load() || !job) { Serial.println("AUDIO_ERROR,0,BUSY"); return true; }
    abort();
    nextSequence = 0;
    active.store(job);
    lastInput = millis();
    Serial.printf("AUDIO_STARTED,%lu\n", job);
    return true;
  }
  if (sscanf(line, "AUDIO_DATA,%lu,%lu,%lu,%lx%n", &job, &sequence, &size, &crc, &used) == 4
      && line[used] == '\0') {
    if (!job || active.load() != job || sequence != nextSequence ||
        size == 0 || size > BLOCK_SIZE || pending || ending || totalBytes + size >= RATE * 60) {
      fail("BAD_FRAME", job);
      return true;
    }
    input.job = job; input.sequence = sequence; input.size = size;
    expectedCRC = crc;
    received = 0;
    lastInput = millis();
    receiving = true;
    return true;
  }
  if (sscanf(line, "AUDIO_END,%lu,%lu%n", &job, &sequence, &used) == 2 && line[used] == '\0') {
    if (!job || active.load() != job || sequence != nextSequence || !sequence || pending || ending) {
      fail("BAD_END", job);
      return true;
    }
    input.job = job; input.sequence = sequence; input.size = 0;
    lastInput = millis();
    pending = ending = true;
    return true;
  }
  fail("BAD_COMMAND", active.load());
  return true;
}
} // namespace GloveAudio

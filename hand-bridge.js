/* Shared, dependency-free protocol and visualization logic (browser + Node tests). */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HandBridge = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const LABELS = { XIN_CHAO: "Xin chào", CAM_ON_NHIEU: "Cảm ơn nhiều", NONE: "Chưa nhận diện" };
  const SENSOR_KEYS = ["flex1", "flex2", "ax", "ay", "az", "gx", "gy", "gz"];
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  function validFlexCalibration(c) {
    return !!c && finite(c.open) && finite(c.closed) && Math.abs(c.closed - c.open) >= 50;
  }
  function restoreCalibration(value) {
    const result = {};
    for (const key of ["flex1", "flex2"]) {
      for (const endpoint of ["open", "closed"]) {
        const sample = value?.[key]?.[endpoint];
        if (finite(sample) && sample >= 0 && sample <= 4095) {
          (result[key] ||= {})[endpoint] = sample;
        }
      }
    }
    return result;
  }
  function validCalibration(c) {
    return !!c && ["flex1", "flex2"].every(k => validFlexCalibration(c[k]));
  }
  function flexValue(raw, calibration) {
    if (!calibration || !finite(raw) || !finite(calibration.open) || !finite(calibration.closed) || Math.abs(calibration.closed - calibration.open) < 50) return 0;
    return clamp((raw - calibration.open) / (calibration.closed - calibration.open), 0, 1) * 1.5;
  }
  function mapFlex(sensors, calibration, flex1Finger) {
    const values = { thumb: 0, Index: 0, Middle: 0, Ring: 0, Pinky: 0 };
    const first = flex1Finger === "Middle" ? "Middle" : "Index";
    values[first] = flexValue(sensors.flex1, calibration && calibration.flex1);
    values[first === "Index" ? "Middle" : "Index"] = flexValue(sensors.flex2, calibration && calibration.flex2);
    return values;
  }
  function canUseDemo(mode) { return mode === "knn_web"; }
  class AutoFlex {
    constructor(isDemo = false) { this.reset(isDemo); }
    reset(isDemo = this.demo) {
      this.demo = isDemo;
      // Approximate live endpoints from this glove's training recordings.
      // The demo generator uses a different range and opposite polarity.
      this.calibration = isDemo
        ? { flex1: { open: 1400, closed: 3000 }, flex2: { open: 1450, closed: 2750 } }
        : { flex1: { open: 931, closed: 833 }, flex2: { open: 1041, closed: 933 } };
      this.recent = { flex1: [], flex2: [] };
      this.startup = { flex1: [], flex2: [] };
      this.filtered = {};
    }
    update(sensors) {
      for (const key of ["flex1", "flex2"]) {
        const raw = sensors[key];
        if (!finite(raw) || raw < 0 || raw > 4095) continue;
        const recent = this.recent[key];
        recent.push(raw);
        if (recent.length > 5) recent.shift();
        const sorted = [...recent].sort((a, b) => a - b);
        const value = sorted[Math.floor(sorted.length / 2)];
        this.filtered[key] = value;
        const c = this.calibration[key];
        const startup = this.startup[key];
        if (startup.length < 20) {
          startup.push(raw);
          // Correct a small wearing offset only near the known open position.
          // Starting with a bent finger must not redefine it as straight.
          if (!this.demo && startup.length === 20 && Math.max(...startup) - Math.min(...startup) <= 16) {
            const mean = startup.reduce((sum, v) => sum + v, 0) / 20;
            if (Math.abs(mean - c.open) <= 25) {
              c.closed += mean - c.open;
              c.open = mean;
            }
          }
        }
        if (recent.length < 5) continue;
        if (this.demo) { c.open = Math.min(c.open, value); c.closed = Math.max(c.closed, value); }
        else { c.open = Math.max(c.open, value); c.closed = Math.min(c.closed, value); }
      }
      return this.calibration;
    }
    map(flex1Finger) {
      const quiet = { ...this.filtered };
      // Ignore small ADC fluctuations while retaining the full bend range.
      for (const key of ["flex1", "flex2"]) {
        const c = this.calibration[key];
        const direction = Math.sign(c.closed - c.open);
        const span = Math.abs(c.closed - c.open);
        const deadzone = this.demo ? 40 : 8;
        const amount = clamp(((quiet[key] - c.open) * direction - deadzone) / (span - deadzone), 0, 1);
        quiet[key] = c.open + amount * (c.closed - c.open);
      }
      return mapFlex(quiet, this.calibration, flex1Finger);
    }
  }
  class Orientation {
    constructor() { this.reset(); }
    reset() { this.time = null; this.roll = 0; this.pitch = 0; this.yaw = 0; this.origin = { roll: 0, pitch: 0, yaw: 0 }; }
    neutral() { this.origin = { roll: this.roll, pitch: this.pitch, yaw: this.yaw }; }
    update(s, time) {
      const roll = Math.atan2(s.ay, s.az);
      const pitch = Math.atan2(-s.ax, Math.hypot(s.ay, s.az));
      // ESP32 millis wraps after ~49 days. A longer gap reinitializes roll/pitch.
      const elapsed = this.time === null ? 0 : ((time - this.time + 4294967296) % 4294967296) / 1000;
      if (!elapsed || elapsed > 0.25) { this.roll = roll; this.pitch = pitch; }
      else {
        const alpha = 0.5 / (0.5 + elapsed);
        const correction = (target, current) => Math.atan2(Math.sin(target - current), Math.cos(target - current));
        this.roll += s.gx * elapsed;
        this.pitch += s.gy * elapsed;
        this.roll += (1 - alpha) * correction(roll, this.roll);
        this.pitch += (1 - alpha) * correction(pitch, this.pitch);
        this.yaw += s.gz * elapsed;
      }
      this.time = time;
      return { roll: this.roll - this.origin.roll, pitch: this.pitch - this.origin.pitch, yaw: this.yaw - this.origin.yaw };
    }
  }
  class Receiver {
    constructor() {
      this.session = null;
      this.retired = new Set();
      this.mode = "python";
      this.clockOffset = 0;
      this.resetSession();
    }
    resetSession() {
      this.seq = -1; this.eventId = -1; this.predictionTime = -1; this.lastLabel = "NONE";
      this.status = null; this.sensor = null; this.lastSensorAt = null; this.lastStatusAt = null;
      this.lastPredictionAt = null; this.prediction = "NONE"; this.confidence = null;
      this.diagnostic = null;
    }
    disconnect() {
      // Preserve sequence/event IDs within a session so reconnect snapshots cannot replay speech.
      this.status = null; this.sensor = null; this.lastSensorAt = null; this.lastStatusAt = null;
      this.lastPredictionAt = null; this.prediction = "NONE"; this.confidence = null;
      this.diagnostic = null;
    }
    clearPrediction() { this.prediction = "NONE"; this.confidence = null; this.lastPredictionAt = null; this.diagnostic = null; }
    sensorFresh(now) { return this.lastSensorAt !== null && now - this.lastSensorAt <= 2000; }
    ready(now) {
      return !!this.status && this.lastStatusAt !== null && now - this.lastStatusAt <= 3500 && this.sensorFresh(now) &&
        ((this.status.esp32_connected && this.status.ai_state === "ready") || (this.status.demo && this.status.ai_state === "demo"));
    }
    expire(now) {
      if (!this.ready(now) || (this.lastPredictionAt !== null && now - this.lastPredictionAt > 2500)) {
        const changed = this.prediction !== "NONE" || this.confidence !== null;
        this.clearPrediction();
        return changed;
      }
      return false;
    }
    accept(packet, now) {
      if (this.mode !== "python" || !packet || packet.version !== 1 || typeof packet.session_id !== "string" || !packet.session_id || typeof packet.demo !== "boolean") return null;
      const p = packet;
      const serverNow = now + this.clockOffset;
      if (p.type === "sensor") {
        if (!Number.isSafeInteger(p.seq) || p.seq < 0 || !Number.isSafeInteger(p.time_ms) || p.time_ms < 0 || !finite(p.received_at_ms) || !p.sensors || !SENSOR_KEYS.every(k => finite(p.sensors[k]))) return null;
        if (p.processed) {
          const q = ["Qw","Qx","Qy","Qz"].map(k => p.processed[k]);
          if (!q.every(finite) || Math.abs(Math.hypot(...q)-1) > .01 || !validCalibration(p.calibration)
              || !["Index","Middle"].includes(p.flex1_finger)
              || !["flex_1_norm","flex_2_norm"].every(k => finite(p.processed[k]) && p.processed[k] >= 0 && p.processed[k] <= 1)) return null;
        }
        if (serverNow - p.received_at_ms > 2000 || p.received_at_ms - serverNow > 5000) return null;
      } else if (p.type === "prediction") {
        if (!Object.prototype.hasOwnProperty.call(LABELS, p.prediction) || !Object.prototype.hasOwnProperty.call(LABELS, p.raw_label) || !finite(p.confidence) || p.confidence < 0 || p.confidence > 1 || typeof p.accepted !== "boolean" || !Number.isSafeInteger(p.event_id) || p.event_id < 0 || !Number.isSafeInteger(p.time_ms) || p.time_ms < 0 || !finite(p.created_at_ms)) return null;
        if (serverNow - p.created_at_ms > 2500 || p.created_at_ms - serverNow > 5000) return null;
        if (!p.accepted && p.prediction !== "NONE") return null;
      } else if (p.type === "status") {
        if (typeof p.esp32_connected !== "boolean" || !["connecting", "warming", "ready", "error", "demo"].includes(p.ai_state) || !Number.isInteger(p.window_count) || !Number.isInteger(p.window_size) || p.window_count < 0 || p.window_size <= 0 || typeof p.message !== "string") return null;
      } else return null;
      let newSession = false;
      if (p.session_id !== this.session) {
        if (this.retired.has(p.session_id) || (this.session !== null && p.type !== "status")) return null;
        if (this.session !== null) this.retired.add(this.session);
        this.session = p.session_id; this.resetSession(); newSession = true;
      }
      let speak = null;
      if (p.type === "status") {
        if (finite(p.server_time_ms)) this.clockOffset = p.server_time_ms - now;
        this.status = p; this.lastStatusAt = now;
        if (!this.ready(now)) this.clearPrediction();
      } else if (p.type === "sensor") {
        if (p.seq <= this.seq) return null;
        this.seq = p.seq; this.sensor = p;
        this.lastSensorAt = now - Math.max(0, serverNow - p.received_at_ms);
      } else {
        if (!this.ready(now) || p.event_id < this.eventId || p.created_at_ms < this.predictionTime) return null;
        const isNewEvent = p.event_id > this.eventId;
        if (isNewEvent && p.accepted) {
          // event_id is authoritative even if a brief rest packet was missed.
          // An unaccepted frame must not consume a later accepted speech event.
          if (p.prediction !== "NONE" && !p.snapshot) speak = LABELS[p.prediction];
          this.lastLabel = p.prediction;
          this.eventId = p.event_id;
        }
        this.predictionTime = p.created_at_ms;
        this.lastPredictionAt = now - Math.max(0, serverNow - p.created_at_ms);
        this.prediction = p.accepted ? p.prediction : "NONE";
        // Confidence belongs to raw_label, never to a rejected gesture's NONE.
        this.confidence = p.accepted && p.prediction !== "NONE" ? p.confidence : null;
        const threshold = finite(p.confidence_threshold) && p.confidence_threshold >= 0 && p.confidence_threshold <= 1 ? p.confidence_threshold : 0.85;
        this.diagnostic = {
          rawLabel: p.raw_label, confidence: p.confidence, accepted: p.accepted,
          threshold, time: p.time_ms,
          reason: !p.accepted ? (p.confidence < threshold ? "low_confidence" : "stabilizing")
            : p.prediction === "NONE" ? "rest" : p.snapshot ? "snapshot" : isNewEvent ? "new" : "repeat",
          stableCount: Number.isInteger(p.stable_count) ? p.stable_count : null,
          stableRequired: Number.isInteger(p.stable_required) ? p.stable_required : null,
        };
      }
      return { type: p.type, packet: p, speak, newSession };
    }
  }
  return { LABELS, SENSOR_KEYS, validFlexCalibration, restoreCalibration, validCalibration, flexValue, mapFlex, canUseDemo, AutoFlex, Orientation, Receiver };
});

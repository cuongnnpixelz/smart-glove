/* =========================================================
   HAND SIMULATOR — Exact Sample 3D Hand Model & Cel-Shading
   Based on Blender Armature + Skinned Mesh + OutlineEffect
   ========================================================= */

// ==================== STATE ====================
const state = {
  flexTarget: { thumb: 0, Index: 0, Middle: 0, Ring: 0, Pinky: 0 },
  imuTarget: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  prediction: "NONE",
  confidence: null,
  streaming: false,
  autoOrbit: false,
  knnEngine: "python", // Python AI trực tiếp hoặc knn_web (demo riêng)
  sensorMode: "2",      // "2" (ngón trỏ + ngón giữa) hoặc "5" (đầy đủ 5 ngón)
};

const FLEX_MAX = 1.5;
const bridge = new HandBridge.Receiver();
const orientation = new HandBridge.Orientation();
const autoFlex = new HandBridge.AutoFlex();
let flexMode = "auto";
let rawSensors = null;
let liveOrientation = { roll: 0, pitch: 0, yaw: 0 };
let calibration = {};
let flex1Finger = "Index";
let calibrationCapture = null;
let calibrationProfile = "live";
try {
  const saved = JSON.parse(localStorage.getItem("HAND_FLEX_CALIBRATION_V1") || "null");
  if (saved) calibration = HandBridge.restoreCalibration(saved.calibration);
  if (saved?.flexMode === "manual") flexMode = "manual";
  if (saved && saved.flex1Finger === "Middle") flex1Finger = "Middle";
} catch (_) { }

// Sample model standard parameters & bone rotation ranges
const PARAMS = {
  bg: 0x0a0e14,
  hand: 0xE7A183,
  shirt: 0x303030,
  vest: 0xE7D55C,
  wrist: 0.08,
  fingerLength: 1.12, // Tỷ lệ độ dài ngón tay (mặc định dài ra 12%)
  thumbMax: 0.90,
  indexMax: 1.10,
  middleMax: 1.25,
  ringMax: 1.25,
  pinkyMax: 1.15,
  thumbz: -0.15,
  indexz: -0.30,
  middlez: -0.08,
  ringz: 0.22,
  pinkyz: 0.52,
};

// ==================== PRESETS ====================
const PRESETS = {
  HELLO: {
    flex: { thumb: 0.15, Index: 1.45, Middle: 0.05, Ring: 0.15, Pinky: 0.15 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  GOODBYE: {
    flex: { thumb: 0.15, Index: 0.05, Middle: 1.45, Ring: 0.15, Pinky: 0.15 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  CUONG: {
    flex: { thumb: 0.15, Index: 0.05, Middle: 1.45, Ring: 0.15, Pinky: 0.15 },
    imu: { gyroX: 1.30, gyroY: 0.75, gyroZ: 0.75 },
  },
  NICE: {
    flex: { thumb: 0.15, Index: 1.45, Middle: 1.45, Ring: 0.15, Pinky: 0.15 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Tôi tên là Cường": {
    flex: { thumb: 0.15, Index: 0.05, Middle: 1.5, Ring: 0.15, Pinky: 0.15 },
    imu: { gyroX: 1.50, gyroY: 1.09, gyroZ: 0.68 },
  },
  "Rock On / I Love You": {
    flex: { thumb: 0.0, Index: 0.0, Middle: 1.5, Ring: 1.5, Pinky: 0.0 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Raised Hand": {
    flex: { thumb: 0.0, Index: 0.0, Middle: 0.0, Ring: 0.0, Pinky: 0.0 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Peace": {
    flex: { thumb: 1.5, Index: 0.0, Middle: 0.0, Ring: 1.5, Pinky: 1.5 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Raised Finger": {
    flex: { thumb: 1.5, Index: 0.0, Middle: 1.5, Ring: 1.5, Pinky: 1.5 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Hang Loose": {
    flex: { thumb: 0.0, Index: 1.5, Middle: 1.5, Ring: 1.5, Pinky: 0.0 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "FU": {
    flex: { thumb: 1.5, Index: 1.5, Middle: 0.0, Ring: 1.5, Pinky: 1.5 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "At rest": {
    flex: { thumb: 0.20, Index: 0.15, Middle: 0.15, Ring: 0.15, Pinky: 0.20 },
    imu: { gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 },
  },
  "Hello nice to meet you": {
    flex: { thumb: 1.10, Index: 0.15, Middle: 0.10, Ring: 0.10, Pinky: 0.95 },
    imu: { gyroX: 0.72, gyroY: 0.78, gyroZ: 1.05 },
  },
  "Whats you're name?": {
    flex: { thumb: 1.25, Index: 1.05, Middle: 0.05, Ring: 0.05, Pinky: 0.05 },
    imu: { gyroX: 0.71, gyroY: 0.72, gyroZ: 0.74 },
  },
  "How are you?": {
    flex: { thumb: 1.30, Index: 1.20, Middle: 0.10, Ring: 0.10, Pinky: 0.10 },
    imu: { gyroX: 0.70, gyroY: 0.76, gyroZ: 0.73 },
  },
  "Where do you work?": {
    flex: { thumb: 1.35, Index: 1.28, Middle: 1.20, Ring: 0.10, Pinky: 0.10 },
    imu: { gyroX: 0.68, gyroY: 0.80, gyroZ: 0.70 },
  },
  "I am learning sign language": {
    flex: { thumb: 0.15, Index: 1.15, Middle: 1.20, Ring: 1.10, Pinky: 0.15 },
    imu: { gyroX: 0.66, gyroY: 0.82, gyroZ: 0.68 },
  },
  "See you later take care": {
    flex: { thumb: 0.20, Index: 1.05, Middle: 1.10, Ring: 1.15, Pinky: 1.20 },
    imu: { gyroX: 0.78, gyroY: 0.72, gyroZ: 0.71 },
  },
};

// ==================== DOM HELPERS ====================
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ==================== LOG ====================
const logEl = $("#log");
function log(level, msg) {
  if (!logEl) return;
  const t = new Date().toLocaleTimeString("vi-VN");
  const div = document.createElement("div");
  div.className = "log-line";
  for (const [className, value] of [["log-time", `[${t}]`], [`log-${level}`, level], ["", msg]]) {
    const span = document.createElement("span");
    span.className = className;
    span.textContent = value;
    div.appendChild(span);
  }
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
  while (logEl.children.length > 200) logEl.removeChild(logEl.firstChild);
}
$("#btnClearLog")?.addEventListener("click", () => {
  if (logEl) logEl.innerHTML = "";
  log("INFO", "Log cleared");
});

// =========================================================
// AI CLASSIFIER (K-NEAREST NEIGHBORS - K-NN)
// Hỗ trợ cấu hình hiện tại (2 ngón trỏ/giữa + MPU6050)
// và mở rộng mượt mà khi người dùng gắn đủ 5 ngón.
// =========================================================
const KNN_CONFIG = {
  k: 3,                 // Số lượng láng giềng gần nhất
  minConfidence: 0.60,  // Ngưỡng tối thiểu công nhận nhãn (60%)
  maxDistance: 0.95,    // Khoảng cách tối đa để tránh nhận diện nhầm
};

// Trọng số các trục cảm biến (Feature Weights)
function getFeatureWeights() {
  if (state.sensorMode === "5") {
    return {
      thumb: 2.0, Index: 2.2, Middle: 2.2, Ring: 2.0, Pinky: 2.0,
      gyroX: 2.5, gyroY: 0.8, gyroZ: 0.8
    };
  }
  // Mặc định cho 2 cảm biến uốn thực tế (Index, Middle) + MPU-6050:
  // Ngón chưa có cảm biến thật được gán trọng số 0.0 để không gây sai số.
  return {
    thumb: 0.0,
    Index: 2.6,
    Middle: 2.6,
    Ring: 0.0,
    Pinky: 0.0,
    gyroX: 3.2, // Trục nghiêng/ngửa: phân biệt cực tốt giữa CUONG (ngửa tay) và GOODBYE (thẳng tay)
    gyroY: 0.8,
    gyroZ: 0.8
  };
}

// Tập dữ liệu mẫu mặc định (Pre-trained Dataset) cho 4 cử chỉ chính + trạng thái nghỉ
const DEFAULT_KNN_DATASET = [
  // 1. REST (Thả lỏng, 2 ngón duỗi thẳng, tay cân bằng)
  { label: "REST", f: { thumb: 0.15, Index: 0.05, Middle: 0.05, Ring: 0.15, Pinky: 0.15, gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 } },
  { label: "REST", f: { thumb: 0.15, Index: 0.08, Middle: 0.08, Ring: 0.15, Pinky: 0.15, gyroX: 0.72, gyroY: 0.76, gyroZ: 0.75 } },
  { label: "REST", f: { thumb: 0.15, Index: 0.02, Middle: 0.10, Ring: 0.15, Pinky: 0.15, gyroX: 0.78, gyroY: 0.74, gyroZ: 0.75 } },

  // 2. HELLO (Ngón trỏ gập, ngón giữa duỗi, tay bình thường)
  { label: "HELLO", f: { thumb: 0.15, Index: 1.45, Middle: 0.05, Ring: 0.15, Pinky: 0.15, gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 } },
  { label: "HELLO", f: { thumb: 0.15, Index: 1.35, Middle: 0.10, Ring: 0.15, Pinky: 0.15, gyroX: 0.80, gyroY: 0.72, gyroZ: 0.75 } },
  { label: "HELLO", f: { thumb: 0.15, Index: 1.50, Middle: 0.08, Ring: 0.15, Pinky: 0.15, gyroX: 0.70, gyroY: 0.78, gyroZ: 0.75 } },

  // 3. GOODBYE (Ngón trỏ duỗi, ngón giữa gập, tay bình thường)
  { label: "GOODBYE", f: { thumb: 0.15, Index: 0.05, Middle: 1.45, Ring: 0.15, Pinky: 0.15, gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 } },
  { label: "GOODBYE", f: { thumb: 0.15, Index: 0.10, Middle: 1.35, Ring: 0.15, Pinky: 0.15, gyroX: 0.78, gyroY: 0.74, gyroZ: 0.75 } },
  { label: "GOODBYE", f: { thumb: 0.15, Index: 0.06, Middle: 1.50, Ring: 0.15, Pinky: 0.15, gyroX: 0.71, gyroY: 0.76, gyroZ: 0.75 } },

  // 4. CUONG (Ngón giữa gập, ngón trỏ duỗi, TAY NGỬA gyroX >= 1.15)
  { label: "CUONG", f: { thumb: 0.15, Index: 0.05, Middle: 1.45, Ring: 0.15, Pinky: 0.15, gyroX: 1.25, gyroY: 0.75, gyroZ: 0.75 } },
  { label: "CUONG", f: { thumb: 0.15, Index: 0.10, Middle: 1.35, Ring: 0.15, Pinky: 0.15, gyroX: 1.20, gyroY: 0.78, gyroZ: 0.75 } },
  { label: "CUONG", f: { thumb: 0.15, Index: 0.05, Middle: 1.50, Ring: 0.15, Pinky: 0.15, gyroX: 1.35, gyroY: 0.72, gyroZ: 0.75 } },

  // 5. NICE (Cả ngón trỏ và ngón giữa cùng gập)
  { label: "NICE", f: { thumb: 0.15, Index: 1.45, Middle: 1.45, Ring: 0.15, Pinky: 0.15, gyroX: 0.75, gyroY: 0.75, gyroZ: 0.75 } },
  { label: "NICE", f: { thumb: 0.15, Index: 1.35, Middle: 1.35, Ring: 0.15, Pinky: 0.15, gyroX: 0.72, gyroY: 0.78, gyroZ: 0.75 } },
  { label: "NICE", f: { thumb: 0.15, Index: 1.50, Middle: 1.50, Ring: 0.15, Pinky: 0.15, gyroX: 0.78, gyroY: 0.72, gyroZ: 0.75 } },
];

let knnDataset = [];

function loadKnnDataset() {
  try {
    const raw = localStorage.getItem("AIOT_KNN_DATASET");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length >= 3) {
        knnDataset = parsed;
        return;
      }
    }
  } catch (_) { }
  knnDataset = JSON.parse(JSON.stringify(DEFAULT_KNN_DATASET));
}

function saveKnnDataset() {
  try {
    localStorage.setItem("AIOT_KNN_DATASET", JSON.stringify(knnDataset));
  } catch (_) { }
}

function calcWeightedDistance(v1, v2, weights) {
  let sum = 0;
  for (const k in weights) {
    const w = weights[k];
    if (w <= 0) continue;
    const d = (v1[k] ?? 0.75) - (v2[k] ?? 0.75);
    sum += w * d * d;
  }
  return Math.sqrt(sum);
}

// Phân loại K-NN
function knnClassify(currentFeatures) {
  if (!knnDataset || knnDataset.length === 0) {
    return { label: "At rest", confidence: 0, distance: 99 };
  }

  const weights = getFeatureWeights();
  const scored = knnDataset.map((sample) => ({
    label: sample.label,
    dist: calcWeightedDistance(currentFeatures, sample.f, weights)
  }));

  scored.sort((a, b) => a.dist - b.dist);

  const k = Math.min(KNN_CONFIG.k, scored.length);
  const topK = scored.slice(0, k);

  const votes = {};
  let totalVoteWeight = 0;

  topK.forEach((item) => {
    const weight = 1 / (item.dist + 0.05);
    votes[item.label] = (votes[item.label] || 0) + weight;
    totalVoteWeight += weight;
  });

  let bestLabel = "REST";
  let maxWeight = 0;
  for (const label in votes) {
    if (votes[label] > maxWeight) {
      maxWeight = votes[label];
      bestLabel = label;
    }
  }

  const minDistance = topK[0].dist;
  const voteRatio = totalVoteWeight > 0 ? (maxWeight / totalVoteWeight) : 0;
  const proximity = Math.max(0, 1 - (minDistance / KNN_CONFIG.maxDistance));
  const confidence = Math.min(1.0, voteRatio * (0.35 + 0.65 * proximity));

  if (minDistance > KNN_CONFIG.maxDistance || confidence < KNN_CONFIG.minConfidence) {
    return { label: "At rest", confidence: confidence, distance: minDistance };
  }

  if (bestLabel === "REST") {
    return { label: "At rest", confidence: confidence, distance: minDistance };
  }

  return { label: bestLabel, confidence: confidence, distance: minDistance };
}

function getCurrentFeatures() {
  return {
    thumb: flexSprings.thumb.value,
    Index: flexSprings.Index.value,
    Middle: flexSprings.Middle.value,
    Ring: flexSprings.Ring.value,
    Pinky: flexSprings.Pinky.value,
    gyroX: imuSprings.gyroX.value,
    gyroY: imuSprings.gyroY.value,
    gyroZ: imuSprings.gyroZ.value,
  };
}

// =========================================================
// SOUND FEEDBACK — TEXT-TO-SPEECH (TTS)
// Phát bản dịch tiếng Anh qua Web Speech API
// =========================================================
const SOUND = { enabled: true };
const speechReport = { token: 0, active: false, message: "Chưa phát câu nào." };

function stopSpeech(message = "Đã dừng phát tiếng.") {
  speechReport.token++;
  if (speechReport.active) speechReport.message = message;
  speechReport.active = false;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

// Từ điển phát âm cho các cử chỉ
const GESTURE_PHRASES = {
  XIN_CHAO: "Hello",
  CAM_ON_NHIEU: "Thank you very much",
  "Xin chào": "Hello",
  "Cảm ơn nhiều": "Thank you very much",
  NONE: "",
  HELLO: "Hello",
  GOODBYE: "Goodbye",
  CUONG: "My name is Cuong",
  "Toi ten la Cuong": "My name is Cuong",
  NICE: "Nice to meet you",
  INDEX: "Hello",
  MIDDLE: "Goodbye",
  BOTH: "Nice to meet you",
  REST: "",
  "At rest": "",
  Idle: ""
};

const GESTURE_STABLE_MS = 250;
let gestureCandidate = null;
let gestureCandidateStart = 0;
let lastSpokenGesture = null;

let englishVoice = null;
let preferredEnglishVoice = "";
try { preferredEnglishVoice = localStorage.getItem("HAND_EN_VOICE_V1") || ""; } catch (_) { }
const voiceKey = voice => `${voice.voiceURI || voice.name}|${voice.lang}`;
function cacheEnglishVoice() {
  const supported = "speechSynthesis" in window;
  const voices = supported ? window.speechSynthesis.getVoices().filter(v => /^en(?:[-_]|$)/i.test(v.lang || "")) : [];
  englishVoice = voices.find(v => voiceKey(v) === preferredEnglishVoice)
    || voices.find(v => v.default) || voices.find(v => v.localService) || voices[0] || null;
  const select = $("#englishVoiceSelect");
  if (select && document.createElement) {
    const options = [{ value: "", label: voices.length ? "Tự chọn giọng Anh" : "Chưa có giọng tiếng Anh" },
      ...voices.map(v => ({ value: voiceKey(v), label: `${v.name} (${v.lang})` }))];
    select.replaceChildren(...options.map(item => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      return option;
    }));
    select.value = voices.some(v => voiceKey(v) === preferredEnglishVoice) ? preferredEnglishVoice : "";
    select.disabled = !voices.length;
  }
  const status = $("#englishVoiceStatus");
  if (status) status.textContent = !supported ? "Trình duyệt không hỗ trợ đọc văn bản. Hãy mở bằng Chrome hoặc Edge."
    : englishVoice ? `Giọng đang dùng: ${englishVoice.name} · ${englishVoice.lang}`
    : "Chưa tìm thấy giọng tiếng Anh. Mở bằng Chrome hoặc Edge rồi bấm Tải lại giọng.";
}
if ("speechSynthesis" in window) {
  cacheEnglishVoice();
  window.speechSynthesis.onvoiceschanged = cacheEnglishVoice;
}

function speak(text, source = "ai", callbacks = {}) {
  text = GESTURE_PHRASES[text] ?? text;
  if (!text) return false;
  if (!SOUND.enabled) { speechReport.message = "Giọng nói đang TẮT. Bật nút Giọng nói rồi bấm Đọc lại kết quả."; return false; }
  if (!("speechSynthesis" in window)) {
    speechReport.message = "Trình duyệt không hỗ trợ phát giọng nói. Hãy thử Chrome hoặc Edge.";
    log("WARN", "Trình duyệt không hỗ trợ Web SpeechSynthesis");
    return false;
  }
  stopSpeech();
  speechReport.source = source;
  // Setting lang alone permits a browser fallback to a non-English voice.
  // Refresh the list because voices can become available after page load.
  cacheEnglishVoice();
  if (!englishVoice) {
    speechReport.message = "Chưa có giọng tiếng Anh. Bấm Tải lại giọng rồi thử lại.";
    return false;
  }
  const token = speechReport.token;
  try {
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = englishVoice.lang.replace("_", "-");
    utter.rate = 1.0;
    utter.pitch = 1.0;
    utter.voice = englishVoice;
    speechReport.active = true;
    speechReport.message = `Đang chờ phát: “${text}”. Nếu im lặng, bấm Thử loa và kiểm tra âm lượng.`;
    utter.onstart = () => {
      if (token === speechReport.token) {
        speechReport.message = `Đang đọc: “${text}”`;
        callbacks.start?.();
      }
    };
    utter.onend = () => {
      if (token !== speechReport.token) return;
      speechReport.active = false;
      speechReport.message = `Trình duyệt đã phát xong: “${text}”`;
      callbacks.end?.();
    };
    utter.onerror = event => {
      if (token !== speechReport.token) return;
      speechReport.active = false;
      speechReport.message = `Không phát được tiếng (${event.error || "không rõ lỗi"}). Bấm Thử loa; kiểm tra âm lượng và giọng đọc của trình duyệt.`;
      log("WARN", speechReport.message);
      callbacks.error?.();
    };
    window.speechSynthesis.speak(utter);
    return true;
  } catch (e) {
    speechReport.active = false;
    speechReport.message = `Không phát được tiếng: ${e.message}`;
    log("WARN", "Lỗi phát giọng nói: " + e.message);
    return false;
  }
}

// Keep sensor capture independent from presentation: accepted events replay their
// own model window, never a later gesture arriving while speech is still running.
const gesturePlayback = { history: [], queue: [], current: null, latest: null };
function showGesturePose(pose) {
  for (const [key, value] of Object.entries(pose.flex)) {
    state.flexTarget[key] = value;
    flexSprings[key].setTarget(value);
  }
  liveOrientation = { ...pose.orientation };
}
function recordGesturePose(packet, flex, rotation) {
  const pose = { time: packet.time_ms, flex: { ...flex }, orientation: { ...rotation } };
  gesturePlayback.latest = pose;
  if (!packet.snapshot) {
    gesturePlayback.history.push(pose);
    if (gesturePlayback.history.length > 250) gesturePlayback.history.shift();
  }
  if (!gesturePlayback.current) showGesturePose(pose);
}
function queueRecognizedGesture(label, confidence, time) {
  if (!GESTURE_PHRASES[label]) return false;
  const frames = gesturePlayback.history.filter(p => ((time - p.time + 4294967296) % 4294967296) <= 2000);
  if (!frames.length || ((time - frames[frames.length - 1].time + 4294967296) % 4294967296) > 250) {
    speechReport.message = "Không còn đoạn chuyển động tương ứng. Hãy thực hiện lại cử chỉ.";
    return false;
  }
  const first = frames[0].time;
  const clip = frames.map(p => ({ ...p, at: (p.time - first + 4294967296) % 4294967296 }));
  gesturePlayback.queue.push({ label, confidence, clip, duration: Math.max(1200, clip[clip.length - 1].at + 250) });
  updateGesturePlayback(performance.now());
  return true;
}
function startGestureSpeech(item, now) {
  item.blocked = false;
  item.requestedAt = now;
  item.startedAt = SOUND.enabled ? null : now;
  item.audioDone = !SOUND.enabled;
  if (!SOUND.enabled) return;
  const current = () => gesturePlayback.current === item;
  const ok = speak(item.label, "gesture", {
    start: () => { if (current()) item.startedAt = performance.now(); },
    end: () => { if (current()) { item.audioDone = true; item.startedAt ??= performance.now(); } },
    error: () => { if (current()) item.blocked = true; },
  });
  if (!ok) item.blocked = true;
}
function resetGesturePlayback() {
  gesturePlayback.current = null;
  gesturePlayback.queue = [];
  gesturePlayback.history = [];
  gesturePlayback.latest = null;
}
function finishGesturePlayback() {
  gesturePlayback.current = null;
  if (gesturePlayback.latest) showGesturePose(gesturePlayback.latest);
  state.prediction = bridge.prediction;
  state.confidence = bridge.confidence;
}
function updateGesturePlayback(now) {
  if (!gesturePlayback.current && gesturePlayback.queue.length) {
    const item = gesturePlayback.current = gesturePlayback.queue.shift();
    startGestureSpeech(item, now);
  }
  const item = gesturePlayback.current;
  if (!item) return;
  state.prediction = item.label;
  state.confidence = item.confidence;
  if (!SOUND.enabled) {
    item.audioDone = true;
    item.blocked = false;
    item.startedAt ??= now;
  }
  if (!item.blocked && !item.audioDone && now - item.requestedAt > 15000) {
    stopSpeech("Không nhận được phản hồi từ loa. Bấm Thử lại hoặc Bỏ qua.");
    item.blocked = true;
  }
  const elapsed = item.startedAt === null ? 0 : now - item.startedAt;
  const pose = item.clip.findLast(p => p.at <= elapsed) || item.clip[0];
  showGesturePose(pose);
  if (!item.blocked && item.audioDone && elapsed >= item.duration) finishGesturePlayback();
}

// Mở khóa SpeechSynthesis / AudioContext ngay lần tương tác đầu tiên của người dùng
function unlockAudio() {
  if ("speechSynthesis" in window) {
    try {
      const unlock = new SpeechSynthesisUtterance(" ");
      unlock.volume = 0;
      window.speechSynthesis.speak(unlock);
    } catch (_) { }
  }
}
window.addEventListener("pointerdown", unlockAudio, { once: true });
window.addEventListener("click", unlockAudio, { once: true });

// Xử lý AI K-NN và kích hoạt giọng nói theo thời gian thực
function updateKnnAndSpeech(nowMs) {
  if (!HandBridge.canUseDemo(state.knnEngine)) return;
  const feats = getCurrentFeatures();

  if (state.knnEngine === "knn_web") {
    const knnRes = knnClassify(feats);
    state.prediction = knnRes.label;
    state.confidence = knnRes.confidence;
  }

  // Chuẩn hóa nhãn để tra từ điển âm thanh
  let activeLabel = state.prediction || "At rest";
  if (activeLabel.includes("Cường") || activeLabel.includes("Cuong") || activeLabel === "CUONG") {
    activeLabel = "CUONG";
  }

  if (activeLabel !== gestureCandidate) {
    gestureCandidate = activeLabel;
    gestureCandidateStart = nowMs;
  }

  if (nowMs - gestureCandidateStart >= GESTURE_STABLE_MS) {
    if (gestureCandidate !== lastSpokenGesture) {
      lastSpokenGesture = gestureCandidate;
      if (gestureCandidate && gestureCandidate !== "At rest" && gestureCandidate !== "REST" && gestureCandidate !== "Idle") {
        const phrase = GESTURE_PHRASES[gestureCandidate] || gestureCandidate;
        speak(phrase);
        log("PRED", `🗣️ [AI TTS] Phát âm: "${phrase}" (Độ tin cậy: ${(state.confidence * 100).toFixed(0)}%)`);
      }
    }
  }
}

// =========================================================
// BIND K-NN UI & TRAINING MANAGER
// =========================================================
function renderKnnSampleCounts() {
  const container = $("#knnSampleCounts");
  if (!container) return;
  const counts = {};
  knnDataset.forEach((s) => {
    counts[s.label] = (counts[s.label] || 0) + 1;
  });
  let html = '<div style="margin-bottom: 4px; color: var(--text-dim);">Số mẫu đã học:</div>';
  for (const label in counts) {
    html += `<span class="knn-sample-tag"><b>${label}</b>: ${counts[label]}</span>`;
  }
  container.innerHTML = html;
}

function bindKnnUI() {
  loadKnnDataset();
  renderKnnSampleCounts();

  // Nút Giọng nói trên Header
  const btnSound = $("#btnSound");
  if (btnSound) {
    btnSound.classList.toggle("btn-sound-active", SOUND.enabled);
    btnSound.textContent = SOUND.enabled ? "🔊 Giọng nói (BẬT)" : "🔇 Giọng nói (TẮT)";
    btnSound.addEventListener("click", () => {
      unlockAudio();
      SOUND.enabled = !SOUND.enabled;
      if (!SOUND.enabled) stopSpeech("Giọng nói đang TẮT.");
      btnSound.classList.toggle("btn-sound-active", SOUND.enabled);
      btnSound.textContent = SOUND.enabled ? "🔊 Giọng nói (BẬT)" : "🔇 Giọng nói (TẮT)";
      log("INFO", `Hệ thống TTS: ${SOUND.enabled ? "ĐÃ BẬT" : "ĐÃ TẮT"}`);
    });
  }

  // Chọn nguồn AI
  const engineSelect = $("#knnEngineSelect");
  if (engineSelect) {
    engineSelect.value = state.knnEngine;
    engineSelect.addEventListener("change", (e) => {
      disconnectAny();
      stopStream();
      state.knnEngine = e.target.value;
      bridge.mode = state.knnEngine;
      clearLiveState();
      updateModeUI();
      log("INFO", `Chuyển nguồn phân loại sang: ${e.target.selectedOptions[0].text}`);
    });
  }

  // Chọn số lượng sensor
  const sensorModeSelect = $("#knnSensorMode");
  if (sensorModeSelect) {
    sensorModeSelect.value = state.sensorMode;
    sensorModeSelect.addEventListener("change", (e) => {
      state.sensorMode = e.target.value;
      log("INFO", `Chế độ cảm biến K-NN: ${e.target.selectedOptions[0].text}`);
    });
  }

  // Dropdown nhãn huấn luyện
  const trainSelect = $("#trainGestureSelect");
  const customRow = $("#customGestureRow");
  if (trainSelect && customRow) {
    trainSelect.addEventListener("change", () => {
      customRow.style.display = trainSelect.value === "CUSTOM" ? "grid" : "none";
    });
  }

  // Nút Ghi nhận mẫu
  $("#btnRecordSample")?.addEventListener("click", () => {
    if (!HandBridge.canUseDemo(state.knnEngine)) return;
    let label = trainSelect ? trainSelect.value : "HELLO";
    if (label === "CUSTOM") {
      const customInput = $("#customGestureName");
      label = (customInput?.value || "").trim().toUpperCase() || "CUSTOM_GESTURE";
    }
    const currentFeats = getCurrentFeatures();
    knnDataset.push({ label, f: currentFeats });
    saveKnnDataset();
    renderKnnSampleCounts();
    log("INFO", `📸 Đã lưu 1 mẫu mới cho cử chỉ [${label}]! (Tổng: ${knnDataset.length} mẫu)`);
  });

  // Nút Reset Dataset
  $("#btnResetDataset")?.addEventListener("click", () => {
    if (confirm("Bạn có chắc muốn khôi phục tập dữ liệu cử chỉ về mặc định không?")) {
      knnDataset = JSON.parse(JSON.stringify(DEFAULT_KNN_DATASET));
      saveKnnDataset();
      renderKnnSampleCounts();
      log("INFO", "↺ Đã khôi phục tập mẫu K-NN về mặc định.");
    }
  });

  // Nút Xuất JSON
  $("#btnExportDataset")?.addEventListener("click", () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(knnDataset, null, 2));
    const a = document.createElement("a");
    a.setAttribute("href", dataStr);
    a.setAttribute("download", `knn_dataset_${state.sensorMode}sensors.json`);
    document.body.appendChild(a);
    a.click();
    a.remove();
    log("INFO", `💾 Đã xuất file dataset JSON (${knnDataset.length} mẫu).`);
  });
}


// =========================================================
// SPRING PHYSICS
// =========================================================
class Spring {
  constructor(value = 0, stiffness = 140, damping = 18) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.stiffness = stiffness;
    this.damping = damping;
  }
  setTarget(t) { this.target = t; }
  update(dt) {
    const h = Math.min(dt, 0.033);
    const force = (this.target - this.value) * this.stiffness;
    const damp = -this.velocity * this.damping;
    const acc = force + damp;
    this.velocity += acc * h;
    this.value += this.velocity * h;
  }
}

const flexSprings = {
  thumb: new Spring(0.0, 140, 16),
  Index: new Spring(0.0, 150, 17),
  Middle: new Spring(0.0, 150, 17),
  Ring: new Spring(0.0, 150, 17),
  Pinky: new Spring(0.0, 140, 16),
};
const imuSprings = {
  gyroX: new Spring(0.75, 120, 16),
  gyroY: new Spring(0.75, 120, 16),
  gyroZ: new Spring(0.75, 120, 16),
};

// =========================================================
// THREE.JS GLOBALS
// =========================================================
let scene, camera, renderer, controls, outlineEffect;
let handGroup = null;
let clock;
let handModelLoaded = false;

// Bone references extracted from GLTF
const handBones = {
  wrist: null,
  wristBones: [],
  thumb: [],
  index: [],
  middle: [],
  ring: [],
  pinky: [],
};

// Rest-pose transforms saved at model load time
const restRotations = new Map();
const restPositions = new Map();
const restScales = new Map();

// Materials
let handMaterial = null;
let shirtMaterial = null;
let vestMaterial = null;
let modelFrame = null;

function measureHandBounds() {
  // Three r128's Box3.setFromObject uses the bind-pose geometry bounds.
  // Measure skinned vertices after bone transforms so fingers stay in frame.
  handGroup.updateMatrixWorld(true);
  const bounds = new THREE.Box3();
  const vertex = new THREE.Vector3();
  handGroup.traverse(mesh => {
    const positions = mesh.geometry?.attributes?.position;
    if (!mesh.isMesh || !positions) return;
    if (mesh.isSkinnedMesh) mesh.skeleton.update();
    for (let index = 0; index < positions.count; index++) {
      vertex.fromBufferAttribute(positions, index);
      if (mesh.isSkinnedMesh) mesh.boneTransform(index, vertex);
      bounds.expandByPoint(vertex.applyMatrix4(mesh.matrixWorld));
    }
  });
  return bounds;
}

function fitHandView() {
  if (!camera || !modelFrame) return;
  const vertical = THREE.MathUtils.degToRad(camera.fov) / 2;
  const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
  const distance = 1.18 * Math.max(
    modelFrame.size.y / (2 * Math.tan(vertical)),
    modelFrame.size.x / (2 * Math.tan(horizontal))
  ) + modelFrame.size.z / 2;
  camera.position.copy(modelFrame.center).add(new THREE.Vector3(0, 0, distance));
  camera.lookAt(modelFrame.center);
  if (controls) {
    controls.target.copy(modelFrame.center);
    controls.minDistance = distance * 0.4;
    controls.maxDistance = distance * 3;
    controls.update();
  }
}

// =========================================================
// INIT THREE.JS SCENE
// =========================================================
function initThree() {
  if (typeof THREE === "undefined") throw new Error("Three.js chưa được nạp.");

  const canvas = $("#canvas");
  const wrap = canvas.parentElement;

  scene = new THREE.Scene();

  const w = wrap.clientWidth || 800;
  const h = wrap.clientHeight || 600;

  // Camera setup matching sample
  camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
  camera.position.set(0, 0.2, 5.0);
  camera.lookAt(0, 0.2, 0);

  renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.shadowMap.enabled = false;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Outline effect
  if (typeof THREE.OutlineEffect === "function") {
    outlineEffect = new THREE.OutlineEffect(renderer, {
      defaultThickness: 0.0035,
      defaultColor: [0, 0, 0],
      defaultAlpha: 0.85,
      defaultKeepAlive: true,
    });
  }

  // OrbitControls
  if (typeof THREE.OrbitControls === "function") {
    controls = new THREE.OrbitControls(camera, canvas);
    controls.target.set(0, 0.2, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 2.5;
    controls.maxDistance = 10;
  }

  // Lights matching sample aesthetics
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.55);
  scene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.75);
  keyLight.position.set(-5, 5, 5);
  keyLight.castShadow = false;
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0xbad2ff, 0.25);
  fillLight.position.set(5, 3, 4);
  scene.add(fillLight);

  // Group to contain hand and apply IMU rotations / auto-orbit
  handGroup = new THREE.Group();
  handGroup.position.set(0, -0.3, 0);
  scene.add(handGroup);

  // Load the 3D hand model
  loadHandModel();

  window.addEventListener("resize", onResize);
  onResize();
}

function onResize() {
  if (!renderer || !camera) return;
  const wrap = $("#canvas")?.parentElement;
  if (!wrap) return;
  const w = Math.max(1, wrap.clientWidth), h = Math.max(1, wrap.clientHeight);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  if (outlineEffect) {
    outlineEffect.setSize(w, h);
    outlineEffect.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  }
  fitHandView();
}

// =========================================================
// LOAD GLTF MODEL & SETUP MATERIALS
// =========================================================
function loadHandModel() {
  const loadingEl = $("#loading");
  if (loadingEl) {
    loadingEl.textContent = "Đang tải mô hình 3D Blender…";
  }

  // Setup gradient texture for Toon Cel-Shading (created programmatically for reliability)
  const gradCanvas = document.createElement('canvas');
  gradCanvas.width = 4;
  gradCanvas.height = 1;
  const gCtx = gradCanvas.getContext('2d');
  ['#555555', '#999999', '#cccccc', '#ffffff'].forEach((c, i) => {
    gCtx.fillStyle = c; gCtx.fillRect(i, 0, 1, 1);
  });
  const gradientTexture = new THREE.CanvasTexture(gradCanvas);
  gradientTexture.minFilter = THREE.NearestFilter;
  gradientTexture.magFilter = THREE.NearestFilter;
  gradientTexture.generateMipmaps = false;

  // Toon Materials with proper skin color
  handMaterial = new THREE.MeshToonMaterial({
    color: new THREE.Color(PARAMS.hand),
    gradientMap: gradientTexture,
    skinning: true,
    emissive: new THREE.Color(0x6b3a2a),
    emissiveIntensity: 0.12,
  });

  shirtMaterial = new THREE.MeshToonMaterial({
    color: new THREE.Color(PARAMS.shirt),
    gradientMap: gradientTexture,
    skinning: true,
    emissive: new THREE.Color(0x111111),
    emissiveIntensity: 0.1,
  });

  vestMaterial = new THREE.MeshToonMaterial({
    color: new THREE.Color(PARAMS.vest),
    gradientMap: gradientTexture,
    skinning: true,
    emissive: new THREE.Color(0x443311),
    emissiveIntensity: 0.1,
  });

  const onModelLoaded = (gltf) => {
    // Thêm cả gltf.scene vào handGroup để getObjectByName bên dưới còn tìm được mesh/skeleton
    handGroup.add(gltf.scene);

    // Apply materials
    const handMesh = gltf.scene.getObjectByName("Hand");
    const shirtMesh = gltf.scene.getObjectByName("Shirt");
    const vestMesh = gltf.scene.getObjectByName("Vest");

    if (handMesh) {
      handMesh.material = handMaterial;
      handMesh.castShadow = false;
      handMesh.receiveShadow = false;
    }
    if (shirtMesh) {
      shirtMesh.material = shirtMaterial;
      shirtMesh.castShadow = false;
      shirtMesh.receiveShadow = false;
    }
    if (vestMesh) {
      vestMesh.material = vestMaterial;
      vestMesh.castShadow = false;
      vestMesh.receiveShadow = false;
    }

    // Cache bones from Armature
    cacheBones(gltf.scene);

    // Fit the full hand and cuff at startup, including narrow split-screen views.
    const bounds = measureHandBounds();
    modelFrame = { center: bounds.getCenter(new THREE.Vector3()), size: bounds.getSize(new THREE.Vector3()) };
    fitHandView();

    handModelLoaded = true;
    log("INFO", "Đã nạp mô hình 3D Armature thành công!");

    if (loadingEl) {
      loadingEl.classList.add("hide");
    }
  };

  const gltfLoader = new THREE.GLTFLoader();

  // Try loading hand.glb file, fallback to embedded data URI if offline/file protocol
  const modelUrl = "hand.glb";

  gltfLoader.load(
    modelUrl,
    onModelLoaded,
    undefined,
    (err) => {
      log("WARN", "Không fetch được hand.glb trực tiếp, nạp qua bộ nhớ dự phòng…");
      if (window.HAND_GLB_DATA) {
        gltfLoader.load(window.HAND_GLB_DATA, onModelLoaded, undefined, (err2) => {
          log("WARN", "Lỗi nạp mô hình dự phòng: " + err2.message);
          if (loadingEl) loadingEl.textContent = "Lỗi tải 3D: " + err2.message;
        });
      } else {
        if (loadingEl) loadingEl.textContent = "Lỗi tải 3D: " + err.message;
      }
    }
  );
}

// =========================================================
// CACHE BONES & INITIAL SPREAD
// =========================================================
function cacheBones(root) {
  const handMesh = root.getObjectByName("Hand");
  if (!handMesh || !handMesh.skeleton || !handMesh.skeleton.bones) {
    log("WARN", "Không tìm thấy Skeleton trong Hand Mesh!");
    return;
  }

  const bones = handMesh.skeleton.bones;

  // Wrist
  handBones.wrist = bones[0];
  handBones.wristBones = [bones[1], bones[2], bones[6], bones[10], bones[14], bones[18]];

  // Fingers (proximal, intermediate, distal)
  handBones.thumb = [bones[3], bones[4], bones[5]];
  handBones.index = [bones[7], bones[8], bones[9]];
  handBones.middle = [bones[11], bones[12], bones[13]];
  handBones.ring = [bones[15], bones[16], bones[17]];
  handBones.pinky = [bones[19], bones[20], bones[21]];

  // Save rest-pose rotations, positions, and scales for every bone
  bones.forEach((bone) => {
    restRotations.set(bone.name, {
      x: bone.rotation.x,
      y: bone.rotation.y,
      z: bone.rotation.z,
    });
    restPositions.set(bone.name, {
      x: bone.position.x,
      y: bone.position.y,
      z: bone.position.z,
    });
    restScales.set(bone.name, {
      x: bone.scale.x,
      y: bone.scale.y,
      z: bone.scale.z,
    });
  });

  // Kéo dài các ngón tay theo tỷ lệ đã đặt
  setFingerLength(PARAMS.fingerLength);

  // Do NOT override any bone rotations — the rest pose from the GLTF is correct
  log("INFO", `Đã lưu rest-pose cho ${restRotations.size} bones & kéo dài các ngón tay (×${PARAMS.fingerLength})`);
}

// =========================================================
// THAY ĐỔI ĐỘ DÀI CÁC NGÓN TAY (FINGER LENGTH)
// =========================================================
function setFingerLength(multiplier = PARAMS.fingerLength) {
  PARAMS.fingerLength = multiplier;
  if (!handModelLoaded && restPositions.size === 0) return;

  const fingerChains = [
    { mid: handBones.thumb[1], tip: handBones.thumb[2] },
    { mid: handBones.index[1], tip: handBones.index[2] },
    { mid: handBones.middle[1], tip: handBones.middle[2] },
    { mid: handBones.ring[1], tip: handBones.ring[2] },
    { mid: handBones.pinky[1], tip: handBones.pinky[2] },
  ];

  fingerChains.forEach(({ mid, tip }) => {
    if (mid && restPositions.has(mid.name)) {
      const origMidPos = restPositions.get(mid.name);
      mid.position.y = origMidPos.y * multiplier;
    }
    if (tip && restPositions.has(tip.name)) {
      const origTipPos = restPositions.get(tip.name);
      tip.position.y = origTipPos.y * multiplier;
    }
    if (tip && restScales.has(tip.name)) {
      const origTipScale = restScales.get(tip.name);
      tip.scale.y = origTipScale.y * multiplier;
    }
  });

  // Đồng bộ với slider trên giao diện (nếu có)
  const slider = $("#sliderFingerLength");
  const valEl = $("#fingerLenVal");
  const hintEl = $("#fingerLenHint");
  if (slider && document.activeElement !== slider) {
    slider.value = multiplier.toFixed(2);
  }
  if (valEl) valEl.textContent = multiplier.toFixed(2) + "×";
  if (hintEl) {
    const pct = Math.round((multiplier - 1) * 100);
    hintEl.textContent = pct >= 0 ? `+${pct}%` : `${pct}%`;
  }
}

// =========================================================
// APPLY SENSOR STATE → 3D BONES & ROTATIONS
// =========================================================
function applyStateToHand(dt) {
  // Luôn cập nhật spring để JSON/IMU panel chạy dù model 3D chưa nạp
  Object.keys(flexSprings).forEach((k) => flexSprings[k].update(dt));
  Object.keys(imuSprings).forEach((k) => imuSprings[k].update(dt));

  if (!handModelLoaded || !handGroup || restRotations.size === 0) return;

  // Bend a finger: ADD flex rotation to rest-pose on the X axis
  function bendFinger(fingerBones, springValue, maxBend) {
    const bend = (Math.max(0, Math.min(FLEX_MAX, springValue)) / FLEX_MAX) * maxBend;
    fingerBones.forEach((bone) => {
      const rest = restRotations.get(bone.name);
      if (!rest) return;
      bone.rotation.x = rest.x + bend;
      bone.rotation.y = rest.y;
      bone.rotation.z = rest.z;
    });
  }

  bendFinger(handBones.thumb, flexSprings.thumb.value, PARAMS.thumbMax);
  bendFinger(handBones.index, flexSprings.Index.value, PARAMS.indexMax);
  bendFinger(handBones.middle, flexSprings.Middle.value, PARAMS.middleMax);
  bendFinger(handBones.ring, flexSprings.Ring.value, PARAMS.ringMax);
  bendFinger(handBones.pinky, flexSprings.Pinky.value, PARAMS.pinkyMax);

  // Handle hand tilt from IMU (gyroX, gyroY, gyroZ)
  const gx = (imuSprings.gyroX.value - 0.75) * 2;
  const gy = (imuSprings.gyroY.value - 0.75) * 2;
  const gz = (imuSprings.gyroZ.value - 0.75) * 2;

  // Tăng biên độ góc quay mô hình 3D (từ 35°/20° lên 50°/42°) và tốc độ bám (dt * 14) giúp phản hồi nhạy bén tức thì
  const live = state.knnEngine === "python";
  const targetRotX = live ? -liveOrientation.pitch : -gx * THREE.MathUtils.degToRad(50);
  const targetRotY = live ? liveOrientation.yaw : gy * THREE.MathUtils.degToRad(50);
  const targetRotZ = live ? liveOrientation.roll : gz * THREE.MathUtils.degToRad(42);

  handGroup.rotation.x += (targetRotX - handGroup.rotation.x) * Math.min(1, dt * 14);
  if (!state.autoOrbit) {
    handGroup.rotation.y += (targetRotY - handGroup.rotation.y) * Math.min(1, dt * 14);
  }
  handGroup.rotation.z += (targetRotZ - handGroup.rotation.z) * Math.min(1, dt * 14);
}

// =========================================================
// UI BINDINGS
// =========================================================
function bindSliders() {
  $$('.slider-row[data-sensor]').forEach((row) => {
    const sensor = row.dataset.sensor;
    const input = row.querySelector("input");
    const valEl = row.querySelector(".val");
    input.addEventListener("input", () => {
      if (!HandBridge.canUseDemo(state.knnEngine)) return;
      const v = parseFloat(input.value);
      state.flexTarget[sensor] = v;
      flexSprings[sensor]?.setTarget(v);
      valEl.textContent = v.toFixed(2);
    });
  });

  $$('.slider-row[data-imu]').forEach((row) => {
    const key = row.dataset.imu;
    const input = row.querySelector("input");
    input.addEventListener("input", () => {
      if (!HandBridge.canUseDemo(state.knnEngine)) return;
      const v = parseFloat(input.value);
      state.imuTarget[key] = v;
      imuSprings[key]?.setTarget(v);
      updateImuDisplay();
    });
  });

  const fingerLenSlider = $("#sliderFingerLength");
  if (fingerLenSlider) {
    fingerLenSlider.addEventListener("input", () => {
      const v = parseFloat(fingerLenSlider.value);
      setFingerLength(v);
    });
  }
}

function updateImuDisplay() {
  const live = state.knnEngine === "python" && bridge.sensorFresh(Date.now());
  for (const axis of ["gx", "gy", "gz", "ax", "ay", "az"]) {
    const el = $("#" + axis + "Val");
    if (el) el.textContent = live && rawSensors ? rawSensors[axis].toFixed(2) : "—";
  }
}

function updateSlidersUI() {
  Object.keys(flexSprings).forEach((sensor) => {
    const row = $(`.slider-row[data-sensor="${sensor}"]`);
    if (!row) return;
    // Use target value so slider doesn't fight with user dragging
    const v = state.flexTarget[sensor] ?? flexSprings[sensor].value;
    row.querySelector("input").value = v;
    row.querySelector(".val").textContent = v.toFixed(2);
  });
  ["gyroX", "gyroY", "gyroZ"].forEach((key) => {
    const row = $(`.slider-row[data-imu="${key}"]`);
    if (!row) return;
    row.querySelector("input").value = state.imuTarget[key] ?? imuSprings[key].value;
  });
  updateImuDisplay();
}

function updateOverlays() {
  const p = $("#prediction");
  const c = $("#confidence");
  const label = HandBridge.LABELS[state.prediction] || state.prediction;
  const confidenceText = state.confidence === null ? "—" : `${Math.round(state.confidence * 100)}%`;
  const source = state.knnEngine === "knn_web" ? "DEMO K-NN" : bridge.status?.demo ? "DEMO Python" : "AI Python";
  if (p) p.textContent = label;
  if (c) c.textContent = `${source} · confidence: ${confidenceText}`;
  const poseStatus = $("#poseStatus");
  if (poseStatus) {
    const calibrated = ["flex1", "flex2"].filter(key => HandBridge.validFlexCalibration(calibration[key]));
    poseStatus.textContent = gesturePlayback.current ? "3D: phát lại cử chỉ đang đọc (theo thứ tự)" : state.knnEngine === "knn_web" ? "3D: tư thế mô phỏng" : !bridge.sensorFresh(Date.now()) ? "3D: chờ dữ liệu cảm biến" : bridge.sensor?.processed ? "3D: mốc hiệu chuẩn và IMU từ Python v2" : flexMode === "auto" ? "3D: tự động theo cảm biến uốn" : calibrated.length === 2 ? "3D: hai ngón đã hiệu chuẩn" : calibrated.length === 1 ? `3D: ${calibrated[0]} đã sẵn sàng; hiệu chuẩn cảm biến còn lại` : "3D: đang dùng mốc thủ công, cần ghi đủ duỗi và gập";
    poseStatus.classList.toggle("needs-calibration", state.knnEngine === "python" && flexMode === "manual" && calibrated.length < 2);
  }

  // Đồng bộ sang panel AI Classifier K-NN
  const knnLabel = $("#knnResultLabel");
  const knnConf = $("#knnConfVal");
  const knnBar = $("#knnConfBar");
  if (knnLabel) {
    knnLabel.textContent = label;
    knnLabel.style.color = (state.prediction === "NONE" || state.prediction === "At rest" || state.prediction === "REST" || state.prediction === "Idle")
      ? "var(--text-dim)" : "var(--success)";
  }
  const pct = Math.round(state.confidence * 100);
  if (knnConf) knnConf.textContent = confidenceText;
  if (knnBar) {
    knnBar.style.width = `${pct}%`;
    knnBar.style.background = pct >= 70
      ? "linear-gradient(90deg, #10b981, #00f2fe)"
      : "linear-gradient(90deg, #f59e0b, #10b981)";
  }

  const j = {
    thumb: flexSprings.thumb.value.toFixed(2),
    Index: flexSprings.Index.value.toFixed(2),
    Middle: flexSprings.Middle.value.toFixed(2),
    Ring: flexSprings.Ring.value.toFixed(2),
    Pinky: flexSprings.Pinky.value.toFixed(2),
    gyroX: imuSprings.gyroX.value.toFixed(2),
    gyroY: imuSprings.gyroY.value.toFixed(2),
    gyroZ: imuSprings.gyroZ.value.toFixed(2),
  };
  const jv = $("#jsonView");
  if (jv) jv.textContent = JSON.stringify(state.knnEngine === "python" ? rawSensors || { status: "Chờ cảm biến" } : j, null, 2);
}

// =========================================================
// PRESETS
// =========================================================
function buildPresetUI() {
  const grid = $("#presetGrid");
  if (!grid) return;
  grid.innerHTML = "";
  Object.keys(PRESETS).forEach((name) => {
    const btn = document.createElement("button");
    btn.className = "preset-btn";
    btn.textContent = name;
    btn.addEventListener("click", () => {
      applyPreset(name);
      $$(".preset-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
    grid.appendChild(btn);
  });
  if (grid.firstChild) grid.firstChild.classList.add("active");
}

function applyPreset(name) {
  if (!HandBridge.canUseDemo(state.knnEngine)) return;
  const p = PRESETS[name];
  if (!p) return;

  Object.keys(p.flex).forEach((k) => {
    state.flexTarget[k] = p.flex[k];
    flexSprings[k]?.setTarget(p.flex[k]);
  });
  Object.keys(p.imu).forEach((k) => {
    state.imuTarget[k] = p.imu[k];
    imuSprings[k]?.setTarget(p.imu[k]);
  });

  state.prediction = name;
  state.confidence = null;
  updateOverlays();
  log("PRED", `→ ${name}`);
}

// =========================================================
// LIVE STREAM (mock)
// =========================================================
const streamNames = Object.keys(PRESETS);
let streamIndex = 0;
let streamTimer = null;

function startStream() {
  if (!HandBridge.canUseDemo(state.knnEngine)) return;
  state.streaming = true;
  $("#streamStatus") && ($("#streamStatus").textContent = "streaming");
  $("#modeLabel") && ($("#modeLabel").textContent = "Streaming");
  const bs = $("#btnStream");
  if (bs) {
    bs.textContent = "⏸ Dừng stream";
    bs.classList.remove("btn-primary");
    bs.classList.add("btn-ghost");
  }
  log("INFO", "Bắt đầu stream (mock)");
  streamTimer = setInterval(() => {
    const name = streamNames[streamIndex % streamNames.length];
    applyPreset(name);
    $$(".preset-btn").forEach((b) => {
      b.classList.toggle("active", b.textContent === name);
    });
    streamIndex++;
  }, 1400);
}

function stopStream() {
  state.streaming = false;
  $("#streamStatus") && ($("#streamStatus").textContent = "paused");
  $("#modeLabel") && ($("#modeLabel").textContent = "Idle");
  const bs = $("#btnStream");
  if (bs) {
    bs.textContent = "▶ Bắt đầu stream";
    bs.classList.add("btn-primary");
    bs.classList.remove("btn-ghost");
  }
  if (streamTimer) clearInterval(streamTimer);
  streamTimer = null;
  log("INFO", "Stream stopped");
}

$("#btnStream")?.addEventListener("click", () => {
  if (state.streaming) stopStream();
  else startStream();
});

// =========================================================
// BUTTONS
// =========================================================
$("#btnReset")?.addEventListener("click", () => {
  stopStream();
  if (state.knnEngine === "python") {
    orientation.neutral();
    liveOrientation = { roll: 0, pitch: 0, yaw: 0 };
    log("INFO", "Đã đặt hướng bàn tay hiện tại làm hướng trung tính.");
    return;
  }
  applyPreset("Rock On / I Love You");
  $$(".preset-btn").forEach((b) => b.classList.remove("active"));
  const first = $$(".preset-btn")[0];
  if (first) first.classList.add("active");
  log("INFO", "Reset tư thế về Rock On / I Love You");
});

$("#btnCalibrate")?.addEventListener("click", () => {
  orientation.neutral();
  liveOrientation = { roll: 0, pitch: 0, yaw: 0 };
  log("INFO", "Đã đặt hướng trung tính. Góc yaw vẫn có thể trôi do MPU6050 không có la bàn.");
});

$("#btnAutoOrbit")?.addEventListener("click", () => {
  state.autoOrbit = !state.autoOrbit;
  log("INFO", `Auto orbit: ${state.autoOrbit ? "ON" : "OFF"}`);
});

$("#btnFullscreen")?.addEventListener("click", () => {
  const el = document.documentElement;
  if (!document.fullscreenElement) el.requestFullscreen();
  else document.exitFullscreen();
});

// Theme toggle (Original sample purple, Dark Sci-fi, Cyberpunk violet)
const bgThemes = [
  "radial-gradient(ellipse 75% 65% at 50% 45%, #5952cf 0%, #3b359c 55%, #231f6d 100%)", // Sample signature purple (#4b46b2)
  "radial-gradient(ellipse 70% 60% at 50% 45%, #1e2a3a 0%, #0b1119 55%, #05080d 100%)", // Dark Sci-Fi
  "radial-gradient(ellipse at center, #2e1065 0%, #17072e 70%, #0c021a 100%)",          // Deep Violet
];
let currentBgIdx = 0;
$("#btnTheme")?.addEventListener("click", () => {
  currentBgIdx = (currentBgIdx + 1) % bgThemes.length;
  const wrap = $(".canvas-wrap");
  if (wrap) wrap.style.background = bgThemes[currentBgIdx];
  log("INFO", `Đổi màu nền canvas (${currentBgIdx + 1}/${bgThemes.length})`);
});

// Save image / screenshot like the sample
$("#btnScreenshot")?.addEventListener("click", () => {
  if (outlineEffect) outlineEffect.render(scene, camera);
  else renderer.render(scene, camera);
  const canvas = $("#canvas");
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = url;
    a.download = `hand-model-${canvas.width}x${canvas.height}.png`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      a.remove();
    }, 1000);
    log("INFO", "Đã lưu ảnh chụp 3D vào máy!");
  });
});

// =========================================================
// ANIMATION LOOP
// =========================================================
let breathingPhase = 0;

let _lastT = performance.now();
function animate() {
  requestAnimationFrame(animate);

  const now = performance.now();
  updateGesturePlayback(now);
  const dt = Math.min((now - _lastT) / 1000, 0.05);
  _lastT = now;

  if (state.autoOrbit && handGroup) handGroup.rotation.y += dt * 0.25;

  applyStateToHand(dt);
  updateKnnAndSpeech(now);

  if (handGroup) {
    breathingPhase += dt * 1.2;
    handGroup.position.y = -0.3 + Math.sin(breathingPhase) * 0.02;
  }

  if (controls && typeof controls.update === "function") controls.update();

  if (renderer && scene && camera) {
    if (outlineEffect) outlineEffect.render(scene, camera);
    else renderer.render(scene, camera);
  }

  if (!animate._uiTick || now - animate._uiTick > 60) {
    animate._uiTick = now;
    updateSlidersUI();
    updateOverlays();
  }
}

// =========================================================
// BOOT
// =========================================================
function boot() {
  // --- UI (độc lập với Three.js) ---
  try {
    bindSliders();
    buildPresetUI();
    bindKnnUI();
    bindSerial();
    updateSlidersUI();
    updateOverlays();
  } catch (err) {
    console.error(err);
    log("WARN", "Lỗi UI: " + err.message);
  }

  // --- 3D ---
  try {
    clock = new THREE.Clock();
    initThree();
    log("INFO", "Hand Simulator 3D (Blender Armature) khởi động thành công!");
    log("INFO", "Chạy SmartSignLanguage/wifi_ai.py → kết nối Python → cử động tay. Hai ngón 3D tự động theo cảm biến.");
  } catch (err) {
    console.error(err);
    const loading = $("#loading");
    if (loading) {
      loading.textContent = "Lỗi 3D: " + err.message;
      loading.style.color = "#ef4444";
    }
    log("WARN", err.message);
  }

  animate();
}

if (document.readyState === "complete") boot();
else window.addEventListener("load", boot);

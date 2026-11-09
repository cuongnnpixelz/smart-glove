/* Python WebSocket connection and calibration UI for mophong1.js. */
const conn = { ws: null, wanted: false, retryTimer: null, attempt: 0, packetCount: 0, rateWindow: [], status: "idle" };

function cancelSpeech() {
  resetGesturePlayback();
  stopSpeech("Đã dừng phát vì đổi nguồn hoặc mất dữ liệu AI.");
  gestureCandidate = null;
  lastSpokenGesture = null;
}

function clearLiveState() {
  bridge.disconnect();
  autoFlex.reset(calibrationProfile === "demo");
  state.autoOrbit = false;
  rawSensors = null;
  const liveValues = $("#flexLiveValues");
  if (liveValues) liveValues.textContent = "ADC hiện tại: chờ cảm biến";
  orientation.reset();
  liveOrientation = { roll: 0, pitch: 0, yaw: 0 };
  calibrationCapture = null;
  state.prediction = "NONE";
  state.confidence = null;
  for (const key of Object.keys(flexSprings)) {
    state.flexTarget[key] = 0;
    flexSprings[key].setTarget(0);
  }
  cancelSpeech();
  updateCalibrationUI();
  updateConnectionStatus();
  updateOverlays();
}

function setConnUI(st, detail = "") {
  conn.status = st;
  $("#connDot").className = "dot " + ({ connected: "dot-green", connecting: "dot-yellow", error: "dot-red" }[st] || "dot-gray");
  $("#connLabel").textContent = st === "connected" ? "Python: đã kết nối" : st === "connecting" ? "Python: đang kết nối…" : "Python: ngắt kết nối";
  $("#connState").textContent = detail || st;
  $("#btnConnect").disabled = conn.wanted || state.knnEngine !== "python";
  $("#btnDisconnect").disabled = !conn.wanted;
  $("#connWsUrl").disabled = conn.wanted;
}

function updateConnectionStatus() {
  const now = Date.now();
  const current = bridge.lastStatusAt !== null && now - bridge.lastStatusAt <= 3500;
  const status = current ? bridge.status : null;
  const fresh = bridge.sensorFresh(now);
  const demo = state.knnEngine === "knn_web" || !!status?.demo;
  $("#esp32Label").textContent = demo ? "Dữ liệu mô phỏng" : status?.esp32_connected ? fresh ? "ESP32: có dữ liệu" : "ESP32: chờ dữ liệu" : "ESP32: chưa kết nối";
  const labels = { connecting: "Chờ ESP32", warming: "Đang lấy mẫu", ready: "Sẵn sàng", error: "Lỗi AI", demo: "DEMO" };
  const ai = state.knnEngine === "knn_web" ? "DEMO K-NN" : status ? `${labels[status.ai_state]} (${status.window_count}/${status.window_size})` : "Chờ Python";
  $("#aiStateLabel").textContent = ai;
  $("#knnStatusBadge").textContent = ai;
  $("#modeLabel").textContent = demo ? "DEMO" : "AI Python";
  $("#bridgeMessage").textContent = status?.message || (conn.status === "connected" ? "Chờ trạng thái từ Python…" : "Chạy wifi_ai.py trên máy tính rồi bấm Kết nối.");
  if (status && !fresh && status.esp32_connected) $("#bridgeMessage").textContent = "Dữ liệu cảm biến đã dừng; kết quả cũ được xóa.";
  updateRecognitionUI();
}

function currentRecognition() {
  return state.knnEngine === "python" && bridge.ready(Date.now()) && bridge.lastPredictionAt !== null
    && Date.now() - bridge.lastPredictionAt <= 2500 ? bridge.diagnostic : null;
}

function updateRecognitionUI() {
  const d = currentRecognition();
  const raw = $("#aiRawLabel");
  if (!raw) return;
  raw.textContent = d ? `AI đang đoán: ${d.rawLabel === "NONE" ? "Tư thế nghỉ" : HandBridge.LABELS[d.rawLabel]} (${d.rawLabel}) · ${(d.confidence * 100).toFixed(1)}%` : "AI đang đoán: chờ kết quả mới";
  const reasons = {
    low_confidence: `Chưa chấp nhận: chưa đạt ngưỡng ${((d?.threshold ?? 0.85) * 100).toFixed(0)}%. Nếu làm đúng mà thường xuyên gặp trạng thái này, cần kiểm tra dữ liệu train.`,
    stabilizing: `Đang chờ nhãn ổn định${d?.stableCount !== null && d?.stableRequired > 0 ? ` (${d.stableCount}/${d.stableRequired})` : ""}.`,
    rest: "Đã nhận tư thế nghỉ. Sẵn sàng đọc lượt cử chỉ tiếp theo.",
    new: "Đã chấp nhận cử chỉ mới; xem trạng thái phát tiếng bên dưới.",
    repeat: "Cử chỉ này đã được nhận. Bấm Đọc lại kết quả, hoặc về tư thế nghỉ rồi làm lại.",
    snapshot: "Kết quả có sẵn khi kết nối. Bấm Đọc lại kết quả nếu muốn nghe.",
  };
  $("#aiDecision").textContent = d ? reasons[d.reason] : state.knnEngine !== "python" ? "Đang ở chế độ DEMO offline. Chọn AI Python để kiểm tra găng thật." : "Chờ dữ liệu cảm biến và kết quả AI mới từ Python.";
  const lag = d && bridge.sensor ? (bridge.sensor.time_ms - d.time + 4294967296) % 4294967296 : null;
  $("#aiSampleLag").textContent = lag !== null && lag < 2147483648 ? `Mẫu cuối AI đã xét cách cảm biến mới nhất ${lag} ms. AI xét một đoạn chuyển động, không chỉ tư thế tức thời.` : "";
  $("#speechStatus").textContent = SOUND.enabled ? speechReport.message : "Giọng nói đang TẮT. Bật nút Giọng nói trên đầu trang.";
  $("#btnReplaySpeech").disabled = !d?.accepted || d.rawLabel === "NONE" || !SOUND.enabled;
  const playing = gesturePlayback.current;
  $("#playbackStatus").textContent = playing
    ? `${playing.blocked ? "Tạm dừng" : "Đang phát"}: ${HandBridge.LABELS[playing.label]} — ${GESTURE_PHRASES[playing.label]} · Chờ ${gesturePlayback.queue.length} cử chỉ`
    : "Chờ cử chỉ mới; tay 3D đang theo cảm biến trực tiếp.";
  $("#btnRetryGesture").hidden = !playing?.blocked;
  $("#btnSkipGesture").hidden = !playing;
  $("#btnTestSpeech").disabled = !!playing;
  $("#btnReplaySpeech").disabled ||= !!playing;
}

function updateModeUI() {
  const demo = HandBridge.canUseDemo(state.knnEngine);
  $$("[data-demo-only]").forEach(el => { el.hidden = !demo; });
  $$(".slider-row[data-sensor] input, .slider-row[data-imu] input, .preset-btn, #btnStream, #knnSensorMode").forEach(el => { el.disabled = !demo; });
  $("#liveCalibration").hidden = demo;
  $("#btnConnect").disabled = demo || conn.wanted;
  $("#sensorHint").textContent = demo ? "DEMO: chỉnh cả 5 ngón" : "2 ngón thật; Cái / Áp út / Út mô phỏng duỗi";
  updateConnectionStatus();
  updateOverlays();
}

function saveCalibration() {
  const key = calibrationProfile === "demo" ? "HAND_FLEX_CALIBRATION_V1_DEMO" : "HAND_FLEX_CALIBRATION_V1";
  try { localStorage.setItem(key, JSON.stringify({ calibration, flex1Finger, flexMode })); }
  catch (_) { log("WARN", "Trình duyệt không lưu được hiệu chuẩn; dữ liệu sẽ mất khi tải lại trang."); }
}

function selectCalibrationProfile(isDemo) {
  const next = isDemo ? "demo" : "live";
  if (next === calibrationProfile) return;
  calibrationProfile = next;
  autoFlex.reset(isDemo);
  flexMode = "auto";
  calibrationCapture = null;
  calibration = {};
  flex1Finger = "Index";
  const key = isDemo ? "HAND_FLEX_CALIBRATION_V1_DEMO" : "HAND_FLEX_CALIBRATION_V1";
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null");
    if (saved) calibration = HandBridge.restoreCalibration(saved.calibration);
    if (saved?.flexMode === "manual") flexMode = "manual";
    if (saved?.flex1Finger === "Middle") flex1Finger = "Middle";
  } catch (_) { }
  $("#flexMapping").value = flex1Finger;
  updateCalibrationUI();
}

function updateCalibrationUI(message) {
  const calibratedV2 = state.knnEngine === "python" && bridge.sensorFresh(Date.now()) && bridge.sensor?.processed && bridge.sensor?.calibration;
  for (const id of ["#flexMode", "#flexMapping", "#btnFlexReset"]) $(id).disabled = !!calibratedV2;
  if (calibratedV2) {
    $("#manualCalibration").hidden = true;
    $("#calibrationStatus").textContent = "Mốc từ phiên hiệu chuẩn Python v2; tay 3D và AI dùng cùng mốc. Hiệu chuẩn lại khi tháo/đeo găng.";
    $("#calibrationValues").textContent = ["flex1","flex2"].map(k => `${k}: ${bridge.sensor.calibration[k].open.toFixed(0)} → ${bridge.sensor.calibration[k].closed.toFixed(0)}`).join(" · ");
    $("#flexMapping").value = bridge.sensor.flex1_finger;
    return;
  }
  const ready = ["flex1", "flex2"].filter(key => HandBridge.validFlexCalibration(calibration[key]));
  const hint = ready.length === 2 ? `Đã hiệu chuẩn. flex1 → ${flex1Finger === "Index" ? "Trỏ" : "Giữa"}.` : ready.length === 1 ? `${ready[0]} đã sẵn sàng. Cảm biến còn lại cần ghi đủ hai mốc cách nhau ít nhất 50 ADC.` : "AI vẫn đọc cử chỉ, nhưng 3D cần hiệu chuẩn: duỗi cả hai ngón và ghi mốc 1, sau đó gập cả hai ngón và ghi mốc 2.";
  $("#flexMode").value = flexMode;
  $("#manualCalibration").hidden = flexMode !== "manual";
  $("#calibrationStatus").textContent = message || (flexMode === "auto" ? "Tự động: cứ duỗi/gập tay, không cần bấm ghi mốc. Mốc có sẵn cho găng hiện tại và tự mở rộng theo cử động." : hint);
  $("#calibrationValues").textContent = ["flex1", "flex2"].map(k => {
    const value = (flexMode === "auto" ? autoFlex.calibration : calibration)[k];
    const span = Number.isFinite(value?.open) && Number.isFinite(value?.closed) ? ` (chênh ${Math.abs(value.closed - value.open).toFixed(0)})` : "";
    return `${k}: ${value?.open?.toFixed(0) ?? "—"} → ${value?.closed?.toFixed(0) ?? "—"}${span}`;
  }).join(" · ");
  $("#btnFlexOpen").disabled = !!calibrationCapture;
  $("#btnFlexClosed").disabled = !!calibrationCapture;
}

function beginCalibration(endpoint) {
  if (state.knnEngine !== "python" || !bridge.sensorFresh(Date.now()) || conn.status !== "connected") {
    updateCalibrationUI("Cần dữ liệu cảm biến mới từ Python để ghi mẫu.");
    return;
  }
  calibrationCapture = { endpoint, samples: [], start: Date.now() };
  updateCalibrationUI(`Giữ yên hai ngón ${endpoint === "open" ? "duỗi" : "gập"}… đang lấy 20 mẫu.`);
}

function captureCalibration(sensors) {
  if (!calibrationCapture) return;
  const capture = calibrationCapture;
  capture.samples.push([sensors.flex1, sensors.flex2]);
  if (capture.samples.length < 20) return;
  const proposed = JSON.parse(JSON.stringify(calibration));
  for (const [i, key] of ["flex1", "flex2"].entries()) {
    proposed[key] = proposed[key] || {};
    proposed[key][capture.endpoint] = capture.samples.reduce((sum, sample) => sum + sample[i], 0) / capture.samples.length;
  }
  calibrationCapture = null;
  // Keep each newly measured endpoint, even if it is close to an old opposite
  // endpoint. Otherwise reversing a sensor's range can lock recalibration.
  calibration = proposed;
  saveCalibration();
  const incomplete = ["flex1", "flex2"].filter(key => !Number.isFinite(proposed[key].open) || !Number.isFinite(proposed[key].closed));
  const failed = ["flex1", "flex2"].filter(key => !incomplete.includes(key) && !HandBridge.validFlexCalibration(proposed[key]));
  const message = failed.length ? `${failed.join(", ")}: hai mốc chênh dưới 50 ADC. Giữ đúng tư thế rồi ghi lại; ngón đã đủ mốc vẫn hoạt động.` : incomplete.length ? `Đã ghi mốc ${capture.endpoint === "open" ? "duỗi" : "gập"}. ${capture.endpoint === "open" ? "Gập cả hai ngón và bấm 2. Ghi khi gập." : "Duỗi cả hai ngón và bấm 1. Ghi khi duỗi."}` : undefined;
  updateCalibrationUI(message);
}

function applyLiveSensors(packet) {
  rawSensors = { ...packet.sensors };
  if (!packet.snapshot) {
    autoFlex.update(rawSensors);
    if (flexMode === "manual") captureCalibration(rawSensors);
  }
  let flex = flexMode === "auto" ? autoFlex.map(flex1Finger) : HandBridge.mapFlex(rawSensors, calibration, flex1Finger);
  let rotation = orientation.update(rawSensors, packet.time_ms);
  if (packet.processed && packet.calibration) {
    flex = HandBridge.mapFlex(rawSensors,packet.calibration,packet.flex1_finger);
    const {Qw:w,Qx:x,Qy:y,Qz:z} = packet.processed;
    rotation = {roll:Math.atan2(2*(w*x+y*z),1-2*(x*x+y*y)),
      pitch:Math.asin(Math.max(-1,Math.min(1,2*(w*y-z*x)))),
      yaw:Math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))};
  }
  recordGesturePose(packet, flex, rotation);
  if (packet.processed) updateCalibrationUI();
  const liveValues = $("#flexLiveValues");
  if (liveValues) liveValues.textContent = `ADC hiện tại: flex1 ${rawSensors.flex1.toFixed(0)} · flex2 ${rawSensors.flex2.toFixed(0)} | Độ gập: Trỏ ${flex.Index.toFixed(2)} · Giữa ${flex.Middle.toFixed(2)}`;
}

function handleLine(line) {
  let packet;
  try { packet = JSON.parse(line); } catch (_) { return; }
  const result = bridge.accept(packet, Date.now());
  if (!result) return;
  if (result.type === "status") selectCalibrationProfile(result.packet.demo);
  if (result.newSession) { orientation.reset(); autoFlex.reset(calibrationProfile === "demo"); calibrationCapture = null; rawSensors = null; cancelSpeech(); updateCalibrationUI(); }
  if (result.type === "sensor") {
    conn.packetCount++;
    conn.rateWindow.push(Date.now());
    applyLiveSensors(result.packet);
  }
  if (!gesturePlayback.current) {
    state.prediction = bridge.prediction;
    state.confidence = bridge.confidence;
  }
  if (result.type === "status" && !bridge.ready(Date.now()) && speechReport.source !== "test") cancelSpeech();
  if (result.speak) {
    queueRecognizedGesture(result.packet.prediction, result.packet.confidence, result.packet.time_ms);
    log("PRED", `${result.packet.demo ? "[DEMO] " : ""}AI đã nhận: ${result.speak} (${Math.round(bridge.confidence * 100)}%)`);
  }
  updateConnectionStatus();
  updateOverlays();
}

function scheduleReconnect() {
  if (!conn.wanted || state.knnEngine !== "python") return;
  const delay = Math.min(15000, 1000 * 2 ** Math.min(conn.attempt++, 4));
  setConnUI("connecting", `Thử lại sau ${delay / 1000}s`);
  conn.retryTimer = setTimeout(connectWs, delay);
}

function connectWs() {
  if (!conn.wanted || state.knnEngine !== "python") return;
  const url = $("#connWsUrl").value.trim();
  let parsed;
  try { parsed = new URL(url); } catch (_) { }
  if (!parsed || !["ws:", "wss:"].includes(parsed.protocol)) {
    conn.wanted = false;
    setConnUI("error", "URL phải có dạng ws://localhost:8765");
    return;
  }
  setConnUI("connecting");
  let ws;
  try { ws = new WebSocket(url); }
  catch (error) { log("WARN", error.message); scheduleReconnect(); return; }
  conn.ws = ws;
  const timeout = setTimeout(() => { if (conn.ws === ws && ws.readyState === WebSocket.CONNECTING) ws.close(); }, 10000);
  ws.onopen = () => {
    if (conn.ws !== ws) return;
    clearTimeout(timeout);
    conn.attempt = 0;
    setConnUI("connected", "WebSocket v1");
    log("INFO", "Đã kết nối Python. Đang chờ dữ liệu ESP32 / AI.");
  };
  ws.onmessage = event => {
    if (conn.ws !== ws || state.knnEngine !== "python" || typeof event.data !== "string") return;
    for (const line of event.data.split(/\r?\n/)) if (line.trim()) handleLine(line);
  };
  ws.onerror = () => { if (conn.ws === ws) log("WARN", "Không kết nối được Python; kiểm tra chương trình và địa chỉ WebSocket."); };
  ws.onclose = () => {
    clearTimeout(timeout);
    if (conn.ws !== ws) return;
    conn.ws = null;
    clearLiveState();
    scheduleReconnect();
  };
}

function connectSelected() {
  if (state.knnEngine !== "python" || conn.wanted) return;
  stopStream();
  clearLiveState();
  conn.wanted = true;
  conn.attempt = 0;
  conn.packetCount = 0;
  conn.rateWindow = [];
  connectWs();
}

function disconnectAny() {
  conn.wanted = false;
  clearTimeout(conn.retryTimer);
  conn.retryTimer = null;
  const ws = conn.ws;
  conn.ws = null;
  if (ws) ws.close();
  clearLiveState();
  setConnUI("idle");
}

function bindSerial() {
  cacheEnglishVoice();
  $("#btnReloadVoices").addEventListener("click", cacheEnglishVoice);
  $("#englishVoiceSelect").addEventListener("change", event => {
    preferredEnglishVoice = event.target.value;
    try { localStorage.setItem("HAND_EN_VOICE_V1", preferredEnglishVoice); } catch (_) { }
    cacheEnglishVoice();
  });
  const host = location.hostname || "localhost";
  $("#connWsUrl").value = `${location.protocol === "https:" ? "wss" : "ws"}://${host.includes(":") ? `[${host}]` : host}:8765`;
  $("#btnConnect").addEventListener("click", connectSelected);
  $("#btnDisconnect").addEventListener("click", disconnectAny);
  $("#btnTestSpeech").addEventListener("click", () => {
    if (gesturePlayback.current) return;
    speak("Hello. Thank you very much.", "test");
    updateRecognitionUI();
  });
  $("#btnReplaySpeech").addEventListener("click", () => {
    const d = currentRecognition();
    if (!gesturePlayback.current && d?.accepted && d.rawLabel !== "NONE") queueRecognizedGesture(d.rawLabel, d.confidence, d.time);
    updateRecognitionUI();
  });
  $("#btnRetryGesture").addEventListener("click", () => {
    if (gesturePlayback.current?.blocked) startGestureSpeech(gesturePlayback.current, performance.now());
    updateRecognitionUI();
  });
  $("#btnSkipGesture").addEventListener("click", () => {
    stopSpeech("Đã bỏ qua cử chỉ này.");
    finishGesturePlayback();
    updateRecognitionUI();
  });
  $("#flexMode").addEventListener("change", event => {
    flexMode = event.target.value === "manual" ? "manual" : "auto";
    calibrationCapture = null;
    saveCalibration();
    if (bridge.sensor && bridge.sensorFresh(Date.now())) applyLiveSensors({ ...bridge.sensor, snapshot: true });
    updateCalibrationUI();
    updateOverlays();
  });
  $("#btnFlexOpen").addEventListener("click", () => beginCalibration("open"));
  $("#btnFlexClosed").addEventListener("click", () => beginCalibration("closed"));
  $("#btnFlexReset").addEventListener("click", () => {
    calibration = {};
    calibrationCapture = null;
    saveCalibration();
    if (bridge.sensor && bridge.sensorFresh(Date.now())) applyLiveSensors({ ...bridge.sensor, snapshot: true });
    updateCalibrationUI("Đã xóa mốc cũ. Duỗi cả hai ngón và bấm 1. Ghi khi duỗi, sau đó gập và bấm 2. Ghi khi gập.");
    updateOverlays();
  });
  $("#flexMapping").value = flex1Finger;
  $("#flexMapping").addEventListener("change", event => { flex1Finger = event.target.value; saveCalibration(); updateCalibrationUI(); });
  window.addEventListener("beforeunload", disconnectAny);
  setConnUI("idle");
  updateModeUI();
  updateCalibrationUI();
  setInterval(() => {
    const now = Date.now();
    conn.rateWindow = conn.rateWindow.filter(time => now - time < 1000);
    $("#connPkts").textContent = conn.packetCount;
    $("#connRate").textContent = conn.rateWindow.length;
    if (state.knnEngine === "python") {
      if (bridge.expire(now)) {
        state.prediction = "NONE";
        state.confidence = null;
        cancelSpeech();
        updateOverlays();
      }
      if (!bridge.sensorFresh(now) && rawSensors) {
        cancelSpeech();
        state.prediction = "NONE";
        state.confidence = null;
        rawSensors = null;
        autoFlex.reset(calibrationProfile === "demo");
        $("#flexLiveValues").textContent = "ADC hiện tại: dữ liệu đã dừng";
        orientation.reset();
        liveOrientation = { roll: 0, pitch: 0, yaw: 0 };
        for (const key of Object.keys(flexSprings)) { state.flexTarget[key] = 0; flexSprings[key].setTarget(0); }
      }
      if (calibrationCapture && now - calibrationCapture.start > 3000) {
        calibrationCapture = null;
        updateCalibrationUI("Ghi mẫu bị dừng vì thiếu dữ liệu. Kiểm tra ESP32 rồi thử lại.");
      }
      updateConnectionStatus();
      if (!calibrationCapture && flexMode === "auto") updateCalibrationUI();
    }
    updateRecognitionUI();
  }, 250);
}

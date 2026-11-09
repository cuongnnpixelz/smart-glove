/* Run: node tests/web_bridge.test.js (also works with Electron's Node runtime). */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const H = require("../hand-bridge.js");
let count = 0;
function test(name, callback) { callback(); console.log("PASS", name); count++; }
const sensors = { flex1: 1000, flex2: 3000, dFlex1: 0, dFlex2: 0, dFlex1Avg: 0, dFlex2Avg: 0, ax: 0, ay: 0, az: 9.81, gx: 0, gy: 0, gz: 0 };
const base = { version: 1, session_id: "one", demo: false };
const status = (time, extra = {}) => ({ ...base, type: "status", esp32_connected: true, ai_state: "ready", window_count: 50, window_size: 50, message: "Ready", server_time_ms: time, ...extra });
const sensor = (time, seq = 1, extra = {}) => ({ ...base, type: "sensor", seq, time_ms: time, received_at_ms: time, sensors: { ...sensors }, ...extra });
const prediction = (time, event_id, label = "XIN_CHAO", extra = {}) => ({ ...base, type: "prediction", time_ms: time, created_at_ms: time, prediction: label, raw_label: label, confidence: 0.9, accepted: true, event_id, ...extra });
function ready(time = 1000) { const r = new H.Receiver(); r.accept(status(time), time); r.accept(sensor(time), time); return r; }

test("calibration handles reversed ranges, saturation, absent/degenerate ranges and swapped fingers", () => {
  const c = { flex1: { open: 3000, closed: 1000 }, flex2: { open: 1000, closed: 3000 } };
  assert(H.validCalibration(c));
  assert.equal(H.flexValue(2000, c.flex1), 0.75);
  assert.equal(H.flexValue(5000, c.flex1), 0);
  assert.equal(H.flexValue(0, c.flex1), 1.5);
  assert.equal(H.flexValue(100, { open: 100, closed: 100 }), 0);
  assert.equal(H.flexValue(100, null), 0);
  assert.deepEqual(H.mapFlex({ flex1: 1000, flex2: 1000 }, c, "Middle"), { thumb: 0, Index: 0, Middle: 1.5, Ring: 0, Pinky: 0 });
});
test("sensor sequence/session validation prevents stale and malformed frames", () => {
  const r = ready();
  assert.equal(r.accept(sensor(1001, 1), 1001), null);
  assert.equal(r.accept(sensor(1001, 0), 1001), null);
  assert.equal(r.accept(sensor(1001, 2, { sensors: { ...sensors, gx: NaN } }), 1001), null);
  assert.equal(r.accept(sensor(1001, 2, { version: 2 }), 1001), null);
  assert.equal(r.accept(sensor(1001, 2, { session_id: "two" }), 1001), null);
  assert(r.accept(status(1002, { session_id: "two" }), 1002).newSession);
  assert(r.accept(sensor(1002, 1, { session_id: "two" }), 1002));
  assert.equal(r.accept(status(1003), 1003), null);
  assert.equal(r.accept(sensor(0, 2, { session_id: "two" }), 4000), null);
});
test("speech emits once, re-arms on accepted rest, and ignores transient unaccepted rest", () => {
  const r = ready();
  assert.equal(r.accept(prediction(1000, 1), 1000).speak, "Xin chào");
  assert.equal(r.accept(prediction(1001, 1), 1001).speak, null);
  assert.equal(r.accept(prediction(1002, 1, "NONE", { accepted: false, raw_label: "XIN_CHAO" }), 1002).speak, null);
  assert.equal(r.accept(prediction(1003, 1), 1003).speak, null);
  assert.equal(r.accept(prediction(1004, 2, "NONE"), 1004).speak, null);
  assert.equal(r.accept(prediction(1005, 3), 1005).speak, "Xin chào");
  assert.equal(r.accept(prediction(1006, 2, "NONE"), 1006), null);
  assert.equal(r.accept(prediction(1007, 4, "CAM_ON_NHIEU"), 1007).speak, "Cảm ơn nhiều");
});
test("reconnect snapshots update display silently; duplicate events stay silent", () => {
  const r = ready();
  assert.equal(r.accept(prediction(1000, 4, "XIN_CHAO", { snapshot: true }), 1000).speak, null);
  assert.equal(r.accept(prediction(1001, 4), 1001).speak, null);
  r.disconnect();
  assert.equal(r.prediction, "NONE");
  r.accept(status(1100), 1100); r.accept(sensor(1100, 2), 1100);
  assert.equal(r.accept(prediction(1100, 4), 1100).speak, null);
  assert.equal(r.accept(prediction(1101, 5, "NONE"), 1101).speak, null);
  assert.equal(r.accept(prediction(1102, 6), 1102).speak, "Xin chào");
});
test("rejected confidence is hidden and rejected frames cannot consume speech events", () => {
  const r = ready();
  r.accept(prediction(1000, 1, "NONE", { accepted: false, raw_label: "XIN_CHAO", confidence: 0.7 }), 1000);
  assert.equal(r.prediction, "NONE");
  assert.equal(r.confidence, null);
  assert.equal(r.accept(prediction(1001, 1), 1001).speak, "Xin chào");
  assert.equal(r.confidence, 0.9);
  // A higher event ID means the server accepted another gesture, even if a
  // rest packet was missed between two identical gestures.
  assert.equal(r.accept(prediction(1002, 3), 1002).speak, "Xin chào");
  r.accept(prediction(1003, 4, "NONE"), 1003);
  assert.equal(r.confidence, null);
});
test("stale sensors, old predictions and disconnected ESP32 invalidate AI output", () => {
  const r = ready();
  r.accept(prediction(1000, 1), 1000);
  assert.equal(r.expire(3001), true);
  assert.equal(r.prediction, "NONE");
  assert.equal(r.confidence, null);
  r.accept(status(4000), 4000); r.accept(sensor(4000, 2), 4000);
  assert.equal(r.accept(prediction(1000, 2), 4000), null);
  r.accept(prediction(4000, 2), 4000);
  r.accept(status(4001, { esp32_connected: false, ai_state: "connecting" }), 4001);
  assert.equal(r.prediction, "NONE");
  assert.equal(r.accept(prediction(4001, 3), 4001), null);
});
test("status clock offset supports separate PCs and demonstration is explicit", () => {
  const r = new H.Receiver();
  r.accept(status(3601000, { demo: true, esp32_connected: false, ai_state: "demo" }), 1000);
  r.accept(sensor(3601000, 1, { demo: true }), 1000);
  assert(r.ready(1000));
  assert.equal(r.accept(prediction(3601000, 1, "XIN_CHAO", { demo: true }), 1000).speak, "Xin chào");
  assert.equal(r.expire(3100), true);
  r.mode = "knn_web";
  assert.equal(r.accept(sensor(3601001, 2), 1001), null);
});
test("IMU integrates angular rate using sample time and reset neutral", () => {
  const imu = new H.Orientation();
  imu.update(sensors, 1000);
  const pose = imu.update({ ...sensors, gz: 1 }, 1040);
  assert(Math.abs(pose.yaw - 0.04) < 1e-9);
  imu.neutral();
  assert(Math.abs(imu.update(sensors, 1080).yaw) < 1e-9);
  const tilt = new H.Orientation().update({ ...sensors, ay: 9.81, az: 0 }, 0);
  assert(Math.abs(tilt.roll - Math.PI / 2) < 1e-9);
});
test("actual web presets, K-NN and mock cannot change live prediction or pose", () => {
  const context = vm.createContext({ HandBridge: H, console, performance: { now: () => 0 }, localStorage: { getItem: () => null }, document: { querySelector: () => null, querySelectorAll: () => [], readyState: "loading" }, window: { addEventListener() {} } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../mophong1.js"), "utf8"), context);
  vm.runInContext('state.prediction = "XIN_CHAO"; state.confidence = 0.94; applyPreset("HELLO"); updateKnnAndSpeech(1000); startStream();', context);
  assert.equal(vm.runInContext("state.prediction", context), "XIN_CHAO");
  assert.equal(vm.runInContext("state.confidence", context), 0.94);
  assert.equal(vm.runInContext("state.flexTarget.Index", context), 0);
  assert.equal(vm.runInContext("state.streaming", context), false);
  vm.runInContext('state.knnEngine = "knn_web"; applyPreset("HELLO");', context);
  assert.equal(vm.runInContext("state.flexTarget.Index", context), 1.45);
  assert.equal(vm.runInContext("state.confidence", context), null);
});
test("demo calibration cannot replace the real glove calibration", () => {
  const store = new Map();
  const elements = new Map();
  const context = vm.createContext({ HandBridge: H, console, performance: { now: () => 0 },
    localStorage: { getItem: key => store.get(key) || null, setItem: (key, value) => store.set(key, value) },
    document: { querySelector: key => { if (!elements.has(key)) elements.set(key, { addEventListener() {} }); return elements.get(key); }, querySelectorAll: () => [], readyState: "loading" },
    window: { addEventListener() {} } });
  for (const file of ["mophong1.js", "hand-connection.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), context);
  }
  vm.runInContext('calibration = {flex1:{open:1000,closed:2000},flex2:{open:1200,closed:2200}}; saveCalibration(); selectCalibrationProfile(true);', context);
  assert.equal(vm.runInContext('Object.keys(calibration).length', context), 0);
  vm.runInContext('calibration = {flex1:{open:500,closed:3000},flex2:{open:600,closed:3300}}; saveCalibration(); selectCalibrationProfile(false);', context);
  assert.equal(vm.runInContext('calibration.flex1.open', context), 1000);
  assert.equal(JSON.parse(store.get("HAND_FLEX_CALIBRATION_V1_DEMO")).calibration.flex1.open, 500);
});
test("a calibrated finger bends even when the other sensor has no calibration", () => {
  const elements = new Map();
  const context = vm.createContext({ HandBridge: H, console, performance: { now: () => 0 },
    localStorage: { getItem: () => null, setItem() {} },
    document: { querySelector: key => { if (!elements.has(key)) elements.set(key, { addEventListener() {} }); return elements.get(key); }, querySelectorAll: () => [], readyState: "loading" },
    window: { addEventListener() {} } });
  for (const file of ["mophong1.js", "hand-connection.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), context);
  context.packet = { sensors: { ...sensors, flex1: 2000 }, time_ms: 1000 };
  vm.runInContext('flexMode = "manual"; calibration = {flex1:{open:1000,closed:2000}}; applyLiveSensors(packet);', context);
  assert.equal(vm.runInContext('state.flexTarget.Index', context), 1.5);
  assert.equal(vm.runInContext('state.flexTarget.Middle', context), 0);
  assert.equal(vm.runInContext('flexSprings.Index.target', context), 1.5);
  assert.equal(H.restoreCalibration({ flex1: { open: 1000 } }).flex1.open, 1000);
});
test("recalibration can reverse an old sensor range without rejecting both captures", () => {
  const elements = new Map();
  const context = vm.createContext({ HandBridge: H, console, performance: { now: () => 0 },
    localStorage: { getItem: () => null, setItem() {} },
    document: { querySelector: key => { if (!elements.has(key)) elements.set(key, { addEventListener() {} }); return elements.get(key); }, querySelectorAll: () => [], readyState: "loading" },
    window: { addEventListener() {} } });
  for (const file of ["mophong1.js", "hand-connection.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), context);
  vm.runInContext(`
    calibration = {flex1:{open:3000,closed:1000},flex2:{open:3000,closed:1000}};
    calibrationCapture = {endpoint:'open', samples:[]};
    for (let i=0; i<20; i++) captureCalibration({flex1:1000,flex2:1000});
    calibrationCapture = {endpoint:'closed', samples:[]};
    for (let i=0; i<20; i++) captureCalibration({flex1:3000,flex2:3000});
  `, context);
  assert.equal(vm.runInContext('calibration.flex1.open', context), 1000);
  assert.equal(vm.runInContext('calibration.flex1.closed', context), 3000);
  assert.equal(vm.runInContext('HandBridge.validCalibration(calibration)', context), true);
});
test("automatic live mapping bends immediately without manual calibration or AI labels", () => {
  const auto = new H.AutoFlex();
  auto.update({ flex1: 833, flex2: 933 });
  assert.equal(auto.map("Index").Index, 1.5);
  assert.equal(auto.map("Index").Middle, 1.5);
  for (let i = 0; i < 100; i++) auto.update({ flex1: 833, flex2: 933 });
  assert.equal(auto.map("Index").Index, 1.5, "holding bent must not redefine open");
  for (let i = 0; i < 5; i++) auto.update({ flex1: 931, flex2: 1041 });
  assert.equal(auto.map("Index").Index, 0);
  assert.equal(auto.map("Index").Middle, 0);
});
test("automatic mapping corrects a small wearing offset and rejects idle noise and isolated spikes", () => {
  const auto = new H.AutoFlex();
  for (let i = 0; i < 30; i++) auto.update({ flex1: 917 + i % 4, flex2: 1041 + i % 4 });
  assert.equal(auto.map("Index").Index, 0);
  assert.equal(auto.map("Index").Middle, 0);
  const before = JSON.stringify(auto.calibration);
  auto.update({ flex1: 4095, flex2: 0 });
  assert.equal(JSON.stringify(auto.calibration), before);
  assert.equal(auto.map("Index").Index, 0);
  for (let i = 0; i < 5; i++) auto.update({ flex1: 780, flex2: 1041 });
  assert.equal(auto.map("Middle").Middle, 1.5);
  assert.equal(auto.map("Middle").Index, 0);
  assert.equal(auto.calibration.flex1.closed, 780);
});
test("automatic demo and live ranges stay separate and reset on a new stream", () => {
  const auto = new H.AutoFlex(true);
  auto.update({ flex1: 3000, flex2: 2750 });
  assert.equal(auto.map("Index").Index, 1.5);
  auto.reset(false);
  assert.equal(auto.calibration.flex1.open, 931);
  assert.equal(auto.map("Index").Index, 0);
  auto.update({ flex1: 931, flex2: 1041 });
  assert.equal(auto.map("Index").Index, 0);
});
test("actual web defaults to automatic even with legacy saved manual endpoints", () => {
  const elements = new Map();
  const context = vm.createContext({ HandBridge: H, console, performance: { now: () => 0 },
    localStorage: { getItem: () => JSON.stringify({calibration:{flex1:{open:0,closed:4000}}}), setItem() {} },
    document: { querySelector: key => { if (!elements.has(key)) elements.set(key, { addEventListener() {} }); return elements.get(key); }, querySelectorAll: () => [], readyState: "loading" },
    window: { addEventListener() {} } });
  for (const file of ["mophong1.js", "hand-connection.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "..", file), "utf8"), context);
  context.packet = { sensors: { ...sensors, flex1: 833, flex2: 933 }, time_ms: 1000 };
  vm.runInContext('applyLiveSensors(packet)', context);
  assert.equal(vm.runInContext('flexMode', context), "auto");
  assert.equal(vm.runInContext('flexSprings.Index.target', context), 1.5);
  assert.equal(vm.runInContext('flexSprings.Middle.target', context), 1.5);
  assert.equal(vm.runInContext('state.prediction', context), "NONE");
});
test("diagnostics retain rejected raw labels, explain silent repeats, and clear stale results", () => {
  const r = ready();
  r.accept(prediction(1000, 0, "NONE", {accepted:false, raw_label:"CAM_ON_NHIEU", confidence:.7}), 1000);
  assert.equal(r.diagnostic.rawLabel, "CAM_ON_NHIEU");
  assert.equal(r.diagnostic.confidence, .7);
  assert.equal(r.diagnostic.reason, "low_confidence");
  assert.equal(r.confidence, null);
  r.accept(prediction(1001, 0, "NONE", {accepted:false, raw_label:"CAM_ON_NHIEU", stable_count:1, stable_required:2}), 1001);
  assert.equal(r.diagnostic.reason, "stabilizing");
  assert.equal(r.diagnostic.stableCount, 1);
  assert.equal(r.accept(prediction(1002, 1, "CAM_ON_NHIEU"), 1002).speak, "Cảm ơn nhiều");
  assert.equal(r.diagnostic.reason, "new");
  assert.equal(r.accept(prediction(1003, 1, "CAM_ON_NHIEU"), 1003).speak, null);
  assert.equal(r.diagnostic.reason, "repeat");
  r.accept(prediction(1004, 2, "NONE"), 1004);
  assert.equal(r.diagnostic.reason, "rest");
  r.expire(4000);
  assert.equal(r.diagnostic, null);
  r.accept(status(5000), 5000); r.accept(sensor(5000, 2), 5000);
  r.accept(prediction(5000, 3, "XIN_CHAO", {snapshot:true}), 5000);
  assert.equal(r.diagnostic.reason, "snapshot");
  r.disconnect();
  assert.equal(r.diagnostic, null);
});
test("speech reports browser callbacks and ignores cancellation callbacks from older utterances", () => {
  const utterances = [];
  const context = vm.createContext({ HandBridge:H, console, performance:{now:()=>0},
    localStorage:{getItem:()=>null}, document:{querySelector:()=>null, querySelectorAll:()=>[], readyState:"loading"},
    SpeechSynthesisUtterance:function(text) { this.text=text; },
    window:{addEventListener(){}, speechSynthesis:{getVoices:()=>[{name:"English",lang:"en-US"}], cancel(){}, speak:u=>utterances.push(u)}} });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../mophong1.js"), "utf8"), context);
  vm.runInContext('speak("Xin chào")', context);
  assert.equal(vm.runInContext('speechReport.active', context), true);
  vm.runInContext('speak("Cảm ơn nhiều")', context);
  utterances[0].onerror({error:"interrupted"});
  assert(vm.runInContext('speechReport.message.includes("Thank you very much")', context));
  utterances[1].onstart();
  assert(vm.runInContext('speechReport.message.startsWith("Đang đọc")', context));
  utterances[1].onend();
  assert.equal(vm.runInContext('speechReport.active', context), false);
  vm.runInContext('SOUND.enabled=false; speak("Xin chào")', context);
  assert.equal(utterances.length, 2);
  assert(vm.runInContext('speechReport.message.includes("TẮT")', context));
  vm.runInContext('SOUND.enabled=true; speak("Xin chào")', context);
  utterances[2].onerror({error:"not-allowed"});
  assert(vm.runInContext('speechReport.message.includes("not-allowed")', context));
});
test("English speech translates labels, rejects other languages and refreshes voices", () => {
  let voices = [{name:"Vietnamese",lang:"vi-VN",default:true}];
  const utterances = [];
  const context = vm.createContext({ HandBridge:H, console, performance:{now:()=>0},
    localStorage:{getItem:()=>null}, document:{querySelector:()=>null, querySelectorAll:()=>[], readyState:"loading"},
    SpeechSynthesisUtterance:function(text) { this.text=text; },
    window:{addEventListener(){}, speechSynthesis:{getVoices:()=>voices, cancel(){}, speak:u=>utterances.push(u)}} });
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../mophong1.js"),"utf8"),context);
  assert.equal(vm.runInContext('speak("CAM_ON_NHIEU")',context),false);
  assert.equal(utterances.length,0);
  assert(vm.runInContext('speechReport.message.includes("Chưa có giọng tiếng Anh")',context));
  voices.push({name:"David",lang:"en-US",localService:true});
  assert.equal(vm.runInContext('speak("CAM_ON_NHIEU")',context),true);
  assert.equal(utterances[0].text,"Thank you very much");
  assert.equal(utterances[0].lang,"en-US");
  assert.equal(utterances[0].voice.name,"David");
  assert.equal(vm.runInContext('speak("NONE")',context),false);
  assert.equal(utterances.length,1);
});

test("saved English voice is honored; foreign language preferences are ignored", () => {
  const voices=[{name:"Vietnamese",voiceURI:"vi",lang:"vi-VN",default:true},
    {name:"English A",voiceURI:"a",lang:"en-US",localService:true},
    {name:"English B",voiceURI:"b",lang:"en_GB"}];
  const context=vm.createContext({HandBridge:H,console,performance:{now:()=>0},
    localStorage:{getItem:key=>key === "HAND_EN_VOICE_V1" ? "b|en_GB" : null},
    document:{querySelector:()=>null,querySelectorAll:()=>[],readyState:"loading"},
    window:{addEventListener(){},speechSynthesis:{getVoices:()=>voices,cancel(){},speak(){}}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../mophong1.js"),"utf8"),context);
  assert.equal(vm.runInContext('englishVoice.name',context),"English B");
  vm.runInContext('preferredEnglishVoice="vi|vi-VN"; cacheEnglishVoice()',context);
  assert.equal(vm.runInContext('englishVoice.name',context),"English A");
  voices.splice(1);
  context.window.speechSynthesis.onvoiceschanged();
  assert.equal(vm.runInContext('englishVoice',context),null);
});
function playbackHarness() {
  let now=0;
  const utterances=[];
  const context=vm.createContext({HandBridge:H,console,performance:{now:()=>now},
    localStorage:{getItem:()=>null},document:{querySelector:()=>null,querySelectorAll:()=>[],readyState:"loading"},
    SpeechSynthesisUtterance:function(text){this.text=text;},
    window:{addEventListener(){},speechSynthesis:{getVoices:()=>[{name:"English",lang:"en-US"}],cancel(){},speak:u=>utterances.push(u)}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,"../mophong1.js"),"utf8"),context);
  const run=code=>vm.runInContext(code,context);
  const tick=time=>{now=time;run('updateGesturePlayback(performance.now())');};
  run('recordGesturePose({time_ms:0},{Index:0,Middle:0},{roll:0,pitch:0,yaw:0}); recordGesturePose({time_ms:1000},{Index:1,Middle:0},{roll:1,pitch:0,yaw:0})');
  return {run,tick,utterances};
}
test("gesture queue waits for BOTH recorded movement and speech, and isolates live poses",()=>{
  const {run,tick,utterances}=playbackHarness();
  run('queueRecognizedGesture("XIN_CHAO",.9,1000); queueRecognizedGesture("CAM_ON_NHIEU",.95,1000)');
  assert.equal(utterances.length,1);
  assert.equal(utterances[0].text,"Hello");
  utterances[0].onstart();
  run('recordGesturePose({time_ms:1100},{Index:0,Middle:1.5},{roll:2,pitch:0,yaw:0})');
  tick(1500);
  assert.equal(run('state.flexTarget.Index'),1);
  assert.equal(run('state.flexTarget.Middle'),0);
  assert.equal(run('state.prediction'),"XIN_CHAO");
  assert.equal(utterances.length,1);
  utterances[0].onend();
  tick(1600);tick(1610);
  assert.equal(utterances.length,2);
  assert.equal(utterances[1].text,"Thank you very much");
  utterances[1].onstart();utterances[1].onend();
  tick(1700);
  assert.equal(run('gesturePlayback.current.label'),"CAM_ON_NHIEU");
  tick(3000);
  assert.equal(run('gesturePlayback.current'),null);
  assert.equal(run('state.flexTarget.Middle'),1.5);
});
test("speech errors hold queue, retry resumes, timeout blocks and reset ignores old callbacks",()=>{
  const {run,tick,utterances}=playbackHarness();
  run('queueRecognizedGesture("XIN_CHAO",.9,1000);queueRecognizedGesture("CAM_ON_NHIEU",.9,1000)');
  utterances[0].onerror({error:"not-allowed"});
  tick(20000);
  assert.equal(run('gesturePlayback.current.blocked'),true);
  assert.equal(utterances.length,1);
  run('startGestureSpeech(gesturePlayback.current,performance.now())');
  utterances[0].onend();
  assert.equal(run('gesturePlayback.current.audioDone'),false);
  tick(36000);
  assert.equal(run('gesturePlayback.current.blocked'),true);
  run('resetGesturePlayback();stopSpeech()');
  utterances[1].onend();tick(40000);
  assert.equal(run('gesturePlayback.current'),null);
  assert.equal(run('gesturePlayback.queue.length'),0);
});
test("recorded windows honor timestamp rollover, reject missing clips and muted playback completes",()=>{
  const {run,tick}=playbackHarness();
  run('resetGesturePlayback();recordGesturePose({time_ms:4294967000},{Index:1},{roll:0,pitch:0,yaw:0});recordGesturePose({time_ms:100},{Index:0},{roll:0,pitch:0,yaw:0});SOUND.enabled=false');
  assert.equal(run('queueRecognizedGesture("XIN_CHAO",.9,100)'),true);
  assert.equal(run('gesturePlayback.current.clip[1].at'),396);
  tick(1300);
  assert.equal(run('gesturePlayback.current'),null);
  assert.equal(run('queueRecognizedGesture("CAM_ON_NHIEU",.9,10000)'),false);
  assert.equal(run('queueRecognizedGesture("NONE",1,100)'),false);
});
test("v2 sensors accept raw channels and validated calibrated IMU without derivatives", () => {
  const r=ready();
  const packet=sensor(1040,2);
  for(const k of Object.keys(packet.sensors)) if(k.startsWith("dFlex")) delete packet.sensors[k];
  packet.processed={Qw:1,Qx:0,Qy:0,Qz:0,flex_1_norm:.5,flex_2_norm:.5};
  packet.calibration={flex1:{open:1000,closed:800},flex2:{open:1100,closed:900}};
  packet.flex1_finger="Index";
  assert(r.accept(packet,1040));
  packet.seq=3;packet.time_ms=1080;packet.received_at_ms=1080;packet.processed.Qw=2;
  assert.equal(r.accept(packet,1080),null);
});
console.log(`${count} browser logic tests passed.`);

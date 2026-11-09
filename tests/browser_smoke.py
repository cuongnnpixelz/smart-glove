"""Exercise the real page + demo bridge in headless Chrome (no ESP32 needed).

Run with the Python environment used for wifi_ai.py. Output stays in .runtime.
Chrome can be specified via --chrome. No browser automation package is needed.
"""
import argparse
import asyncio
import base64
import functools
import http.server
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request

from websockets.asyncio.client import connect


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class Browser:
    def __init__(self, ws):
        self.ws = ws
        self.counter = 0
        self.exceptions = []

    async def call(self, method, params=None):
        self.counter += 1
        call_id = self.counter
        await self.ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await asyncio.wait_for(self.ws.recv(), 15))
            if message.get("method") == "Runtime.exceptionThrown":
                self.exceptions.append(message["params"]["exceptionDetails"])
            if message.get("id") == call_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    async def evaluate(self, expression):
        result = await self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    async def wait_for(self, expression, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.evaluate(expression):
                return
            await asyncio.sleep(0.2)
        raise AssertionError(f"Browser condition timed out: {expression}")


async def smoke(chrome_path):
    artifacts = ROOT / ".runtime" / "browser-smoke"
    artifacts.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ws_port, cdp_port = free_port(), free_port()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    processes = []
    log_files = []

    def start_bridge():
        log = (artifacts / f"bridge-{len(processes)}.log").open("w", encoding="utf-8")
        log_files.append(log)
        process = subprocess.Popen([
            sys.executable, "-u", "SmartSignLanguage/wifi_ai.py", "--demo",
            "--ws-host", "127.0.0.1", "--ws-port", str(ws_port),
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        processes.append(process)
        return process

    try:
        bridge = start_bridge()
        chrome_log = (artifacts / "chrome.log").open("w", encoding="utf-8")
        log_files.append(chrome_log)
        chrome = subprocess.Popen([
            chrome_path, "--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            f"--remote-debugging-port={cdp_port}", "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={artifacts / ('profile-' + str(int(time.time())))}", "about:blank",
        ], stdout=chrome_log, stderr=subprocess.STDOUT, creationflags=flags)
        processes.append(chrome)
        pages = None
        for _attempt in range(80):
            if chrome.poll() is not None:
                raise RuntimeError(f"Chrome exited: inspect {artifacts / 'chrome.log'}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=1) as response:
                    pages = json.load(response)
                if pages:
                    break
            except OSError:
                pass
            await asyncio.sleep(0.25)
        if not pages:
            raise RuntimeError("Chrome DevTools endpoint didn't start")
        target = next(page for page in pages if page["type"] == "page")
        async with connect(target["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024) as ws:
            browser = Browser(ws)
            await browser.call("Page.enable")
            await browser.call("Runtime.enable")
            await browser.call("Emulation.setDeviceMetricsOverride", {
                "width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False,
            })
            await browser.call("Page.navigate", {
                "url": f"http://127.0.0.1:{server.server_port}/mophong1.html",
            })
            await browser.wait_for("typeof handModelLoaded !== 'undefined' && handModelLoaded")
            # Verify the visible, skinned mesh bounds, not only the GLTF bind pose.
            await browser.wait_for("(() => { camera.updateMatrixWorld(true); const b = measureHandBounds(); return [b.min,b.max].every(v => { const p=v.clone().project(camera); return Math.abs(p.x)<1 && Math.abs(p.y)<1; }); })()")
            assert await browser.evaluate("document.getElementById('knnEngineSelect').value") == "python"
            # Stub speech callbacks; actual speaker output needs a listening check.
            await browser.evaluate("""(() => {
                window.__spoken = []; window.__overlap = false; window.__speaking = false;
                window.SpeechSynthesisUtterance = function(text) { this.text = text; };
                speechSynthesis.getVoices = () => [{name:'Test English',voiceURI:'test-en',lang:'en-US'}];
                speechSynthesis.cancel = () => { clearTimeout(window.__speechTimer); window.__speaking=false; };
                speechSynthesis.speak = u => {
                    if (!u.text.trim()) return;
                    if (window.__speaking) window.__overlap = true;
                    window.__speaking = true;
                    window.__spoken.push({text:u.text,lang:u.lang,label:gesturePlayback.current?.label});
                    u.onstart?.();
                    window.__speechTimer=setTimeout(() => {window.__speaking=false;u.onend?.();},500);
                };
                cacheEnglishVoice();
            })()""")
            await browser.evaluate(
                f"document.getElementById('connWsUrl').value='ws://127.0.0.1:{ws_port}';"
                "document.getElementById('btnConnect').click()"
            )
            await browser.wait_for("Number(document.getElementById('connPkts').textContent) > 20")
            assert await browser.evaluate("flexMode === 'auto' && document.getElementById('manualCalibration').hidden")
            await browser.wait_for("state.flexTarget.Index > 0.5 || state.flexTarget.Middle > 0.5")
            assert await browser.evaluate("Object.keys(calibration).length === 0")
            print("PASS: automatic sensor mapping bends fingers without capturing calibration.")
            await browser.wait_for("!document.getElementById('btnReplaySpeech').disabled", timeout=25)
            assert await browser.evaluate("document.getElementById('aiRawLabel').textContent.includes('%')")
            assert await browser.evaluate("document.getElementById('aiSampleLag').textContent.includes('ms')")
            await browser.wait_for("window.__spoken.some(x=>x.text==='Hello') && window.__spoken.some(x=>x.text==='Thank you very much')", timeout=25)
            assert await browser.evaluate("window.__spoken.every(x=>x.lang==='en-US' && x.text===GESTURE_PHRASES[x.label]) && !window.__overlap")
            await browser.wait_for("!document.getElementById('btnReplaySpeech').disabled", timeout=25)
            assert await browser.evaluate("(() => {const before=bridge.eventId; const count=window.__spoken.length; document.getElementById('btnReplaySpeech').click(); return window.__spoken.length===count+1 && bridge.eventId===before && !!gesturePlayback.current;})()")
            print("PASS: English translations, queued motion playback and manual replay request the matching voice without overlap.")
            await browser.evaluate("document.getElementById('flexMode').value='manual'; document.getElementById('flexMode').dispatchEvent(new Event('change'))")
            # Capture two actual batches from the deterministic demo, using the
            # same buttons and WebSocket sensor stream as the user.
            await browser.wait_for("bridge.sensor && Math.floor(bridge.sensor.time_ms / 4000) % 4 === 2 && bridge.sensor.time_ms % 4000 < 500", timeout=25)
            await browser.evaluate("document.getElementById('btnFlexOpen').click()")
            await browser.wait_for("!calibrationCapture && Number.isFinite(calibration.flex1?.open)")
            await browser.wait_for("bridge.sensor && Math.floor(bridge.sensor.time_ms / 4000) % 4 === 3 && bridge.sensor.time_ms % 4000 < 500", timeout=15)
            await browser.evaluate("document.getElementById('btnFlexClosed').click()")
            await browser.wait_for("!calibrationCapture && HandBridge.validCalibration(calibration)")
            await browser.wait_for("state.flexTarget.Index > 0.5 || state.flexTarget.Middle > 0.5")
            assert await browser.evaluate("localStorage.getItem('HAND_FLEX_CALIBRATION_V1') === null")
            assert await browser.evaluate("localStorage.getItem('HAND_FLEX_CALIBRATION_V1_DEMO') !== null")
            snapshot = await browser.evaluate("JSON.stringify(Object.fromEntries(" 
                "['connLabel','esp32Label','aiStateLabel','prediction','calibrationStatus'].map(id => "
                "[id, document.getElementById(id)?.textContent])))")
            (artifacts / "status.json").write_text(snapshot, encoding="utf-8")
            shot = await browser.call("Page.captureScreenshot", {"format": "png"})
            (artifacts / "connected.png").write_bytes(base64.b64decode(shot["data"]))
            print("PASS: 3D loaded, Python mode default, WebSocket sensors and two-point calibration move fingers.")

            # At split-screen/mobile widths the connection and calibration UI
            # must remain reachable; previous CSS hid the entire sidebar.
            await browser.call("Emulation.setDeviceMetricsOverride", {
                "width": 800, "height": 1000, "deviceScaleFactor": 1, "mobile": False,
            })
            await browser.wait_for("getComputedStyle(document.querySelector('.sidebar')).display !== 'none'")
            await browser.evaluate("document.getElementById('liveCalibration').scrollIntoView()")
            shot = await browser.call("Page.captureScreenshot", {"format": "png"})
            (artifacts / "narrow.png").write_bytes(base64.b64decode(shot["data"]))
            assert await browser.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            print("PASS: narrow layout retains connection/calibration controls without horizontal overflow.")

            previous_count = await browser.evaluate("conn.packetCount")
            previous_session = await browser.evaluate("bridge.session")
            bridge.terminate()
            bridge.wait(timeout=5)
            await asyncio.sleep(3)
            await browser.wait_for("document.getElementById('prediction').textContent.includes('Chưa')")
            bridge = start_bridge()
            await browser.wait_for(
                f"conn.packetCount > {previous_count + 20} && bridge.session !== {json.dumps(previous_session)}"
                " && conn.ws?.readyState === WebSocket.OPEN && bridge.sensorFresh(Date.now())", timeout=25)
            print("PASS: lost bridge clears prediction; automatic reconnect receives telemetry.")
            await browser.evaluate("document.getElementById('btnDisconnect').click()")
            await asyncio.sleep(3)
            assert await browser.evaluate("document.getElementById('btnConnect').disabled") is False
            assert await browser.evaluate("conn.ws === null && !conn.wanted")
            assert await browser.evaluate("document.getElementById('btnReplaySpeech').disabled && bridge.diagnostic === null")
            # Exercise the v2 calibration/IMU path in the real page with a
            # deterministic packet, independently of the legacy demo stream.
            assert await browser.evaluate("""(() => {
                const now=Date.now(), base={version:1,session_id:'v2-browser-fixture',demo:false};
                handleLine(JSON.stringify({...base,type:'status',server_time_ms:now,esp32_connected:true,ai_state:'warming',window_count:1,window_size:50,message:'v2 fixture'}));
                handleLine(JSON.stringify({...base,type:'sensor',seq:1,time_ms:1000,received_at_ms:now,
                  sensors:{flex1:900,flex2:1000,ax:0,ay:0,az:9.81,gx:0,gy:0,gz:0},
                  processed:{Qw:1,Qx:0,Qy:0,Qz:0,flex_1_norm:.5,flex_2_norm:.5},
                  calibration:{flex1:{open:1000,closed:800},flex2:{open:1100,closed:900}},flex1_finger:'Index'}));
                const ok=state.flexTarget.Index===.75 && state.flexTarget.Middle===.75
                  && document.getElementById('calibrationStatus').textContent.includes('Python v2')
                  && document.getElementById('flexMapping').disabled;
                clearLiveState();
                return ok;
            })()""")
            print("PASS: v2 ADC uses Python calibration and quaternion in the real web page.")
            assert not browser.exceptions, browser.exceptions
            print("PASS: manual disconnect stops reconnect; no uncaught browser exceptions.")
            print(f"Screenshot: {artifacts / 'connected.png'}")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        server.shutdown()
        server.server_close()
        for log in log_files:
            log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    args = parser.parse_args()
    asyncio.run(smoke(args.chrome))

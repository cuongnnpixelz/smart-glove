"""ESP32 TCP -> inference -> WebSocket bridge. Python 3.10+.

Run ``python SmartSignLanguage/wifi_ai.py --demo`` without TensorFlow/hardware.
Install requirements.txt for transport; real AI also needs requirements-ai.txt.
Importing this module never loads TensorFlow, opens sockets, or starts threads.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
from contextlib import suppress
import json
import logging
import math
from pathlib import Path
import queue
import threading
import time
import uuid


BASE_DIR = Path(__file__).resolve().parent
WINDOW_SIZE = 50
PREDICT_EVERY = 5
CONFIDENCE_THRESHOLD = 0.85
STABLE_REQUIRED = 2
FEATURE_NAMES = (
    "flex1", "flex2", "dFlex1", "dFlex2", "dFlex1Avg", "dFlex2Avg",
    "ax", "ay", "az", "gx", "gy", "gz",
)
MAX_PREDICTION_AGE = 2.0
MAX_SAMPLE_GAP_MS = 250  # Refill the AI window after a gap in the 25 Hz stream.
LOG = logging.getLogger("glove.bridge")


def epoch_ms():
    return time.time_ns() // 1_000_000


def parse_sensor_line(line):
    """Return (uint32 timestamp, ordered features), or None for malformed input.

    Acceleration is m/s²; gyroscope is rad/s. ADC and derivatives are unchanged.
    Non-DATA messages (including collector BEGIN/END) are intentionally ignored.
    """
    if isinstance(line, bytes):
        try:
            line = line.decode("ascii")
        except UnicodeDecodeError:
            return None
    if len(line) > 2048:
        return None
    parts = line.strip().split(",")
    raw_v2 = len(parts) == 10 and parts[0] == "RAW2"
    if not raw_v2 and (len(parts) != 14 or parts[0] != "DATA"):
        return None
    try:
        if not parts[1].isascii() or not parts[1].isdigit():
            return None
        stamp = int(parts[1])
        features = tuple(float(value) for value in parts[2:])
    except (ValueError, OverflowError):
        return None
    if not 0 <= stamp <= 0xFFFFFFFF or not all(math.isfinite(v) for v in features):
        return None
    if not all(0 <= value <= 4095 for value in features[:2]):
        return None
    if raw_v2:
        # Web v1 aliases only; these zero placeholders never enter a v2 model/CSV.
        features = (*features[:2], 0.0, 0.0, 0.0, 0.0, *features[2:])
    return stamp, features


class AcceptanceFilter:
    """Only confident, stable labels create events; real NONE rearms gestures."""

    def __init__(self):
        self.candidate = None
        self.count = 0
        self.last_accepted = None
        self.event_id = 0

    def update(self, raw_label, confidence):
        if (not isinstance(raw_label, str) or not raw_label or len(raw_label) > 64
                or not raw_label.isascii() or any(c in raw_label for c in ",\r\n")):
            raise ValueError("Invalid model label")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Model confidence must be finite and between 0 and 1")
        if confidence < CONFIDENCE_THRESHOLD:
            self.candidate, self.count = None, 0
            accepted = False
        else:
            self.count = self.count + 1 if self.candidate == raw_label else 1
            self.candidate = raw_label
            accepted = self.count >= STABLE_REQUIRED
        if accepted and self.last_accepted != raw_label:
            self.event_id += 1
            self.last_accepted = raw_label
        return {
            "prediction": raw_label if accepted else "NONE",
            "raw_label": raw_label,
            "confidence": confidence,
            "accepted": accepted,
            "event_id": self.event_id,
            "decision_reason": "accepted" if accepted else "low_confidence" if confidence < CONFIDENCE_THRESHOLD else "stabilizing",
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "stable_count": min(self.count, STABLE_REQUIRED),
            "stable_required": STABLE_REQUIRED,
        }


class ModelPredictor:
    """Loaded only inside the worker; keep the training feature order/scaler."""

    def __init__(self):
        import joblib
        import numpy as np
        import tensorflow as tf

        self.np = np
        self.model = tf.keras.models.load_model(BASE_DIR / "gesture_model.keras")
        self.scaler = joblib.load(BASE_DIR / "gesture_scaler.pkl")
        self.encoder = joblib.load(BASE_DIR / "label_encoder.pkl")
        if tuple(self.model.input_shape[1:]) != (WINDOW_SIZE, len(FEATURE_NAMES)):
            raise ValueError("Model input must be (50, 12)")
        if self.model.output_shape[-1] != len(self.encoder.classes_):
            raise ValueError("Model output does not match label_encoder.pkl")
        LOG.info("Model loaded. Labels: %s", list(self.encoder.classes_))

    def predict(self, window):
        x = self.np.asarray(window, dtype=self.np.float32)
        x = self.scaler.transform(x).astype(self.np.float32)
        output = self.np.asarray(self.model(x[None, ...], training=False))[0]
        if not self.np.isfinite(output).all():
            raise ValueError("Model returned non-finite probabilities")
        index = int(self.np.argmax(output))
        return str(self.encoder.inverse_transform([index])[0]), float(output[index])


class DemoPredictor:
    """Deterministic synthetic labels, explicitly flagged demo in every packet."""

    def predict(self, window):
        flex = window[-1][0]
        label = "NONE" if flex < 1800 else "XIN_CHAO" if flex < 2600 else "CAM_ON_NHIEU"
        return label, 0.96


class Bridge:
    def __init__(self, *, esp32_host="192.168.137.115", esp32_port=5000,
                 ws_host="127.0.0.1", ws_port=8765, demo=False,
                 read_timeout=3.0, reconnect_delay=2.0, predictor_factory=None,
                 pipeline="legacy", calibration=None, model_dir=None):
        self.esp32_host, self.esp32_port = esp32_host, esp32_port
        self.ws_host, self.ws_port = ws_host, ws_port
        self.demo = demo
        self.pipeline = "legacy" if demo else pipeline
        self.processor = None
        if self.pipeline == "v2":
            if __package__:
                from .sensor_pipeline import SensorProcessor, load_calibration, make_window, from_legacy, model_vector
                from .model_v2 import ModelV2
            else:
                from sensor_pipeline import SensorProcessor, load_calibration, make_window, from_legacy, model_vector
                from model_v2 import ModelV2
            c = load_calibration(calibration or BASE_DIR/"calibration"/"current.json")
            self.processor = SensorProcessor(c)
            self.make_window, self.from_legacy, self.model_vector = make_window, from_legacy, model_vector
            predictor_factory = predictor_factory or (lambda: ModelV2(model_dir or BASE_DIR/"models"/"v2",c))
        self.read_timeout, self.reconnect_delay = read_timeout, reconnect_delay
        self.predictor_factory = predictor_factory or (DemoPredictor if demo else ModelPredictor)
        self.clients = {}
        self.jobs = queue.Queue(maxsize=1)
        self.worker_stop = threading.Event()
        self.model_ready = False
        self.model_error = None
        self.esp32_connected = False
        self.writer = None
        self.server = None
        self.tasks = []
        self.session_id = uuid.uuid4().hex
        self._reset_session()

    def _reset_session(self):
        self.session_id = uuid.uuid4().hex
        self.window = deque(maxlen=WINDOW_SIZE)
        self.processed_rows = deque(maxlen=100)
        self.processing_error = None
        if self.processor:
            self.processor.reset()
        self.seq = 0
        self.last_time_ms = None
        self.samples_since_predict = 0
        self.acceptance = AcceptanceFilter()
        self.last_sensor = None
        self.last_prediction = None
        self.last_prediction_at = 0.0
        self.last_lcd = None
        self.last_lcd_at = 0.0
        while True:
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break

    def status(self):
        if self.processing_error:
            state, message = "warming", self.processing_error
        elif self.model_error:
            state, message = "error", self.model_error
        elif self.demo:
            state, message = "demo", "DEMO: synthetic sensors and labels; ESP32 is not connected"
        elif not self.esp32_connected:
            state, message = "connecting", f"Connecting to ESP32 {self.esp32_host}:{self.esp32_port}"
        elif not self.model_ready:
            state, message = "warming", "Loading AI model; sensor streaming remains active"
        elif len(self.window) < WINDOW_SIZE:
            state, message = "warming", f"Collecting samples {len(self.window)}/{WINDOW_SIZE}"
        elif time.monotonic() - self.last_prediction_at > MAX_PREDICTION_AGE:
            state, message = "warming", "Waiting for a fresh AI prediction"
        else:
            state, message = "ready", "ESP32 and AI ready"
        if not self.demo:
            message = ("[V2 calibrated] " if self.processor else "[LEGACY ADC/model cu] ") + message
        return {
            "type": "status", "version": 1, "session_id": self.session_id,
            "esp32_connected": self.esp32_connected, "ai_state": state,
            "window_count": len(self.window), "window_size": WINDOW_SIZE,
            "message": message, "demo": self.demo, "server_time_ms": epoch_ms(),
            "pipeline": self.pipeline,
        }

    def publish(self, packet):
        encoded = json.dumps(packet, separators=(",", ":"), allow_nan=False)
        for websocket, messages in list(self.clients.items()):
            try:
                messages.put_nowait(encoded)
            except asyncio.QueueFull:
                # Disconnect slow browsers instead of delaying TCP sensor ingestion.
                self.clients.pop(websocket, None)
                asyncio.create_task(websocket.close(code=1013, reason="Client too slow; reconnect"))

    async def browser(self, websocket):
        messages = asyncio.Queue(maxsize=64)
        # Register and copy snapshots without yielding, preserving packet order.
        self.clients[websocket] = messages
        snapshots = [self.status(), self.last_sensor]
        if time.monotonic() - self.last_prediction_at <= MAX_PREDICTION_AGE:
            snapshots.append(self.last_prediction)
        for packet in snapshots:
            if packet is not None:
                messages.put_nowait(json.dumps(dict(packet, snapshot=True), allow_nan=False))

        async def send():
            while True:
                await websocket.send(await messages.get())

        sender = asyncio.create_task(send())
        receiver = asyncio.create_task(websocket.wait_closed())
        try:
            await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.clients.pop(websocket, None)
            sender.cancel()
            receiver.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)

    def ingest(self, time_ms, features):
        if self.last_time_ms is not None and (
                time_ms < self.last_time_ms or time_ms - self.last_time_ms > (120 if self.processor else MAX_SAMPLE_GAP_MS)):
            # A reboot, clock wrap or sampling gap cannot mix AI windows.
            self._reset_session()
            self.publish(self.status())
        if time_ms == self.last_time_ms:
            return False
        self.last_time_ms = time_ms
        self.seq += 1
        row = None
        if self.processor:
            try:
                row = self.processor.process(time_ms,self.from_legacy(features))
                self.processed_rows.append(row)
                self.window.append(self.model_vector(row,self.processor.calibration))
                self.processing_error = None if self.processor.ready else "Giu yen luc khoi dong IMU; cho du 2 giay"
            except ValueError as error:
                self._reset_session()
                self.processing_error = str(error)
        else:
            self.window.append(features)
        self.last_sensor = {
            "type": "sensor", "version": 1, "session_id": self.session_id,
            "seq": self.seq, "time_ms": time_ms, "received_at_ms": epoch_ms(),
            "sensors": dict(zip(FEATURE_NAMES, features)), "demo": self.demo,
        }
        if row is not None:
            self.last_sensor["sensors"] = {k:v for k,v in self.last_sensor["sensors"].items() if not k.startswith("dFlex")}
            normalized = self.model_vector(row,self.processor.calibration)
            self.last_sensor["processed"] = {**row,"flex_1_norm":float(normalized[0]),"flex_2_norm":float(normalized[1])}
            self.last_sensor["calibration"] = {"flex1":self.processor.calibration["flex_1"],"flex2":self.processor.calibration["flex_2"]}
            self.last_sensor["flex1_finger"] = self.processor.calibration["flex1_finger"]
        self.publish(self.last_sensor)
        self.samples_since_predict += 1
        if len(self.window) == WINDOW_SIZE and self.samples_since_predict >= PREDICT_EVERY and not self.processing_error:
            self.samples_since_predict = 0
            window = tuple(self.window)
            if self.processor:
                try:
                    window = self.make_window(list(self.processed_rows),self.processor.calibration)
                except ValueError as error:
                    self._reset_session()
                    self.processing_error = str(error)
                    self.publish(self.status())
                    return True
                if window is None:
                    return True
            job = (self.session_id, time_ms, time.monotonic(), window)
            with suppress(queue.Empty):
                self.jobs.get_nowait()
            self.jobs.put_nowait(job)
        if self.seq == 1 or self.seq == WINDOW_SIZE:
            self.publish(self.status())
        return True

    def _model_loaded(self, error=None):
        self.model_ready = error is None
        self.model_error = error
        self.publish(self.status())

    def _worker(self, loop):
        def deliver(callback, *args):
            if not self.worker_stop.is_set():
                with suppress(RuntimeError):
                    loop.call_soon_threadsafe(callback, *args)
        try:
            predictor = self.predictor_factory()
        except Exception as error:
            deliver(self._model_loaded, f"AI unavailable: {error}. Install requirements-ai.txt and verify model files")
            return
        deliver(self._model_loaded)
        while not self.worker_stop.is_set():
            try:
                session, stamp, queued_at, window = self.jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                raw_label, confidence = predictor.predict(window)
                deliver(self._prediction_done, session, stamp, queued_at, raw_label, confidence, None)
            except Exception as error:
                deliver(self._prediction_done, session, stamp, queued_at, None, None, str(error))

    def _prediction_done(self, session, stamp, queued_at, raw_label, confidence, error):
        if session != self.session_id or not (self.demo or self.esp32_connected):
            return
        if time.monotonic() - queued_at > MAX_PREDICTION_AGE:
            return
        if error:
            self.model_error = f"AI inference failed: {error}"
            self.last_prediction = None
            self.acceptance.candidate, self.acceptance.count = None, 0
            self.publish(self.status())
            self._send_lcd(force=True)
            return
        try:
            decision = self.acceptance.update(raw_label, confidence)
        except (TypeError, ValueError) as error:
            self._prediction_done(session, stamp, queued_at, None, None, str(error))
            return
        self.model_error = None
        self.last_prediction_at = time.monotonic()
        self.last_prediction = {
            "type": "prediction", "version": 1, "session_id": session,
            "time_ms": stamp, "created_at_ms": epoch_ms(), "demo": self.demo,
            **decision,
        }
        self.publish(self.status())
        self.publish(self.last_prediction)
        self._send_lcd()

    def _send_lcd(self, force=False):
        if self.writer is None or self.writer.is_closing():
            return
        prediction = self.last_prediction
        fresh = time.monotonic() - self.last_prediction_at <= MAX_PREDICTION_AGE
        if prediction and fresh and prediction["accepted"]:
            label, confidence = prediction["prediction"], prediction["confidence"]
        else:
            label, confidence = "NONE", 0.0
        if force or label != self.last_lcd or time.monotonic() - self.last_lcd_at >= 0.9:
            # Tiny heartbeat; StreamWriter.write never blocks sensor forwarding.
            self.writer.write(f"AI,{label},{confidence * 100:.2f}\n".encode("ascii"))
            self.last_lcd, self.last_lcd_at = label, time.monotonic()

    async def heartbeat(self):
        while True:
            self.publish(self.status())
            self._send_lcd()
            await asyncio.sleep(1)

    async def esp32_stream(self):
        while True:
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.esp32_host, self.esp32_port, limit=4096),
                    timeout=self.read_timeout,
                )
                self.writer = writer
                if self.processor:
                    writer.write(b"RAW2\n")
                    await writer.drain()
                self._reset_session()
                self.esp32_connected = True
                self.publish(self.status())
                self._send_lcd(force=True)
                LOG.info("ESP32 connected, session %s", self.session_id)
                last_valid = time.monotonic()
                while True:
                    remaining = self.read_timeout - (time.monotonic() - last_valid)
                    if remaining <= 0:
                        raise TimeoutError("ESP32 stopped sending valid sensor data")
                    line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                    if not line:
                        raise ConnectionError("ESP32 disconnected")
                    if self.processor and not line.startswith(b"RAW2,"):
                        continue
                    sample = parse_sensor_line(line)
                    if sample is not None:
                        if self.ingest(*sample):
                            last_valid = time.monotonic()
            except (OSError, ValueError, TimeoutError, asyncio.TimeoutError) as error:
                LOG.warning("ESP32: %s; retrying in %.1fs",
                            str(error) or "sensor read/connect timeout", self.reconnect_delay)
            finally:
                self.esp32_connected = False
                self.writer = None
                self._reset_session()  # Invalidates in-flight predictions immediately.
                self.publish(self.status())
                if writer is not None:
                    writer.close()
                    with suppress(OSError, TimeoutError, asyncio.TimeoutError):
                        await asyncio.wait_for(writer.wait_closed(), timeout=1)
            await asyncio.sleep(self.reconnect_delay)

    async def demo_stream(self):
        self._reset_session()
        self.publish(self.status())
        frame = 0
        while True:
            seconds = frame / 25
            phase = int(seconds / 4) % 4
            flex1 = (1400, 2200, 1400, 3000)[phase] + 40 * math.sin(seconds)
            flex2 = 2100 + 650 * math.sin(seconds * 0.8)
            features = (flex1, flex2, 0, 0, 0, 0,
                        math.sin(seconds * 0.5), 0, 9.81, 0, 0.1 * math.sin(seconds), 0)
            self.ingest(frame * 40, features)
            frame += 1
            await asyncio.sleep(0.04)

    async def start(self):
        from websockets.asyncio.server import serve

        self.server = await serve(self.browser, self.ws_host, self.ws_port,
                                  max_size=4096, max_queue=8, close_timeout=1)
        self.ws_port = self.server.sockets[0].getsockname()[1]
        LOG.info("WebSocket ws://%s:%s%s", self.ws_host, self.ws_port,
                 " [DEMO: synthetic data]" if self.demo else "")
        self.worker_stop.clear()
        self.thread = threading.Thread(target=self._worker,
                                       args=(asyncio.get_running_loop(),), daemon=True)
        self.thread.start()
        self.tasks = [asyncio.create_task(self.heartbeat()),
                      asyncio.create_task(self.demo_stream() if self.demo else self.esp32_stream())]
        return self

    async def close(self):
        self.worker_stop.set()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--esp32-host", default="192.168.137.115")
    parser.add_argument("--esp32-port", type=int, default=5000)
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="Synthetic data, no ESP32/TensorFlow")
    parser.add_argument("--pipeline", choices=("v2","legacy"), default="v2", help="v2 needs real calibration and a newly trained bundle; legacy explicitly uses the old model")
    parser.add_argument("--calibration", type=Path, default=BASE_DIR/"calibration"/"current.json")
    parser.add_argument("--model-dir", type=Path, default=BASE_DIR/"models"/"v2")
    return parser


async def run(args):
    bridge = Bridge(**vars(args))
    try:
        await bridge.start()
        await asyncio.gather(*bridge.tasks)
    finally:
        await bridge.close()


def main():
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        LOG.info("Bridge stopped")
    except ImportError as error:
        raise SystemExit(f"Missing bridge dependency: {error}. Run pip install -r SmartSignLanguage/requirements.txt")
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"Cannot start bridge: {error}. V2: run collect_v2.py --user-id YOUR_ID --calibrate-only first; see docs/thu-du-lieu-v2.md")


if __name__ == "__main__":
    main()

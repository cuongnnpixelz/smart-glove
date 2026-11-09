"""Protocol and real loopback TCP/WebSocket integration without AI dependencies."""

import asyncio
from contextlib import suppress
import json
import threading
import time
import unittest

from SmartSignLanguage.wifi_ai import (
    AcceptanceFilter, Bridge, FEATURE_NAMES, parse_sensor_line,
)


FEATURES = (1200, 2200, 1, 2, 3, 4, 0.1, 0.2, 9.81, 0.3, 0.4, 0.5)


def line(stamp, features=FEATURES):
    return ("DATA," + str(stamp) + "," + ",".join(map(str, features)) + "\n").encode()


async def receive_until(websocket, predicate, timeout=4):
    async def read():
        while True:
            packet = json.loads(await websocket.recv())
            if predicate(packet):
                return packet
    return await asyncio.wait_for(read(), timeout)


class ProtocolTests(unittest.TestCase):
    def test_valid_sensor_feature_order_and_units(self):
        stamp, features = parse_sensor_line(line(4294967295))
        self.assertEqual(stamp, 4294967295)
        self.assertEqual(features, FEATURES)
        self.assertEqual(FEATURE_NAMES[6:], ("ax", "ay", "az", "gx", "gy", "gz"))

    def test_malformed_and_nonfinite_are_rejected(self):
        bad = [b"", b"BEGIN\n", b"END\n", line(-1), line(1.5), line(2**32),
               line(1).replace(b"9.81", b"nan"), line(1).replace(b"9.81", b"inf"),
               line(1).replace(b"1200", b"4096"), line(1).replace(b"DATA", b"OTHER"),
               line(1) + b",0", b"DATA,1,\xff\n", b"x" * 5000]
        for value in bad:
            with self.subTest(value=value[:40]):
                self.assertIsNone(parse_sensor_line(value))

    def test_stability_confidence_events_and_rearm_after_rest(self):
        state = AcceptanceFilter()
        self.assertFalse(state.update("XIN_CHAO", .95)["accepted"])
        first = state.update("XIN_CHAO", .95)
        self.assertTrue(first["accepted"])
        self.assertEqual(first["event_id"], 1)
        self.assertEqual(state.update("XIN_CHAO", .99)["event_id"], 1)
        uncertain = state.update("CAM_ON_NHIEU", .55)
        self.assertFalse(uncertain["accepted"])
        self.assertEqual(uncertain["prediction"], "NONE")
        self.assertEqual(uncertain["raw_label"], "CAM_ON_NHIEU")
        self.assertEqual(uncertain["confidence"], .55)
        self.assertEqual(uncertain["event_id"], 1)
        state.update("NONE", .99)
        self.assertEqual(state.update("NONE", .99)["event_id"], 2)
        state.update("XIN_CHAO", .95)
        repeated = state.update("XIN_CHAO", .95)
        self.assertEqual(repeated["event_id"], 3)
        self.assertTrue(repeated["accepted"])

    def test_bad_probabilities_and_protocol_injection_rejected(self):
        for confidence in (float("nan"), float("inf"), -1, 1.1):
            with self.assertRaises(ValueError):
                AcceptanceFilter().update("NONE", confidence)
        with self.assertRaises(ValueError):
            AcceptanceFilter().update("NONE\nAI,XIN_CHAO,100", .99)

    def test_decision_diagnostics_distinguish_uncertainty_stability_and_rest(self):
        state = AcceptanceFilter()
        low = state.update("CAM_ON_NHIEU", .84)
        self.assertEqual(low["decision_reason"], "low_confidence")
        self.assertEqual(low["confidence_threshold"], .85)
        self.assertEqual(low["stable_count"], 0)
        waiting = state.update("CAM_ON_NHIEU", .95)
        self.assertEqual(waiting["decision_reason"], "stabilizing")
        self.assertEqual(waiting["stable_count"], 1)
        accepted = state.update("CAM_ON_NHIEU", .95)
        self.assertEqual(accepted["decision_reason"], "accepted")
        self.assertEqual(accepted["stable_count"], accepted["stable_required"])
        state.update("NONE", .99)
        rest = state.update("NONE", .99)
        self.assertTrue(rest["accepted"])
        self.assertEqual(rest["prediction"], "NONE")

    def test_stale_inference_does_not_change_accepted_state(self):
        bridge = Bridge()
        bridge.esp32_connected = True
        bridge._prediction_done(bridge.session_id, 2000, time.monotonic() - 3,
                                "XIN_CHAO", .99, None)
        self.assertIsNone(bridge.last_prediction)
        self.assertEqual(bridge.acceptance.count, 0)

    def test_sampling_gap_discards_previous_window_and_inflight_prediction(self):
        bridge = Bridge()
        bridge.esp32_connected = True
        for stamp in range(0, 2000, 40):
            bridge.ingest(stamp, FEATURES)
        previous = bridge.session_id
        bridge.ingest(3000, FEATURES)
        self.assertNotEqual(bridge.session_id, previous)
        self.assertEqual(len(bridge.window), 1)
        self.assertEqual(bridge.seq, 1)
        bridge._prediction_done(previous, 1960, time.monotonic(), "XIN_CHAO", .99, None)
        self.assertIsNone(bridge.last_prediction)


class ConstantPredictor:
    def predict(self, window):
        return "XIN_CHAO", .95


class BridgeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from websockets.asyncio.client import connect
        self.connect = connect
        self.connections = asyncio.Queue()
        self.tcp_clients = []
        self.lcd_lines = []

        async def esp32(reader, writer):
            self.tcp_clients.append(writer)
            await self.connections.put(writer)
            try:
                while data := await reader.readline():
                    self.lcd_lines.append(data.decode().strip())
            except (ConnectionError, OSError):
                pass
            finally:
                writer.close()
                with suppress(ConnectionError, OSError):
                    await writer.wait_closed()

        self.tcp = await asyncio.start_server(esp32, "127.0.0.1", 0)
        self.port = self.tcp.sockets[0].getsockname()[1]
        self.bridges = []

    async def asyncTearDown(self):
        for bridge in self.bridges:
            await bridge.close()
        for writer in self.tcp_clients:
            writer.close()
        self.tcp.close()
        await self.tcp.wait_closed()

    async def start_bridge(self, **options):
        kwargs = dict(esp32_host="127.0.0.1", esp32_port=self.port,
                      ws_port=0, read_timeout=1, reconnect_delay=.05,
                      predictor_factory=ConstantPredictor)
        kwargs.update(options)
        bridge = Bridge(**kwargs)
        await bridge.start()
        self.bridges.append(bridge)
        writer = await asyncio.wait_for(self.connections.get(), 2)
        return bridge, writer

    def uri(self, bridge):
        return f"ws://127.0.0.1:{bridge.ws_port}"

    async def test_forwarding_real_websocket_prediction_snapshots_and_lcd(self):
        bridge, writer = await self.start_bridge()
        async with self.connect(self.uri(bridge)) as ws:
            initial = json.loads(await ws.recv())
            self.assertEqual(initial["type"], "status")
            self.assertTrue(initial["snapshot"])
            writer.write(b"HELLO\nDATA,bad\n" + line(40))
            await writer.drain()
            sensor = await receive_until(ws, lambda p: p["type"] == "sensor")
            self.assertEqual(sensor["sensors"]["az"], 9.81)
            self.assertEqual(sensor["sensors"]["gy"], .4)
            self.assertFalse(sensor["demo"])
            session = sensor["session_id"]
            writer.write(b"".join(line(i * 40) for i in range(2, 51)))
            await writer.drain()
            first = await receive_until(ws, lambda p: p["type"] == "prediction")
            self.assertFalse(first["accepted"])
            writer.write(b"".join(line(i * 40) for i in range(51, 56)))
            await writer.drain()
            second = await receive_until(ws, lambda p: p["type"] == "prediction" and p["accepted"])
            self.assertEqual(second["prediction"], "XIN_CHAO")
            self.assertEqual(second["event_id"], 1)
            async with self.connect(self.uri(bridge)) as late:
                snapshots = [json.loads(await late.recv()) for _ in range(3)]
                self.assertEqual([p["type"] for p in snapshots], ["status", "sensor", "prediction"])
                self.assertTrue(all(p["snapshot"] for p in snapshots))
                self.assertTrue(all(p["session_id"] == session for p in snapshots))
                self.assertEqual(snapshots[2]["event_id"], 1)
            await asyncio.sleep(.03)
            self.assertIn("AI,XIN_CHAO,95.00", self.lcd_lines)
            self.assertIn("AI,NONE,0.00", self.lcd_lines)

    async def test_slow_inference_does_not_block_sensors_and_old_session_is_dropped(self):
        gate = threading.Event()
        entered = threading.Event()

        class SlowPredictor:
            def predict(self, window):
                entered.set()
                gate.wait(3)
                return "CAM_ON_NHIEU", .99

        bridge, writer = await self.start_bridge(predictor_factory=SlowPredictor)
        try:
            async with self.connect(self.uri(bridge)) as ws:
                writer.write(b"".join(line(i * 40) for i in range(50)))
                await writer.drain()
                old = await receive_until(ws, lambda p: p["type"] == "sensor" and p["seq"] == 50)
                for _ in range(20):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(entered.is_set())
                writer.write(b"".join(line(i * 40) for i in range(50, 60)))
                await writer.drain()
                streamed = await receive_until(ws, lambda p: p["type"] == "sensor" and p["seq"] == 60)
                self.assertEqual(streamed["session_id"], old["session_id"])
                self.assertLessEqual(bridge.jobs.qsize(), 1)
                writer.close()
                replacement = await asyncio.wait_for(self.connections.get(), 2)
                replacement.write(line(0))
                await replacement.drain()
                new = await receive_until(ws, lambda p: p["type"] == "sensor" and p["session_id"] != old["session_id"])
                self.assertEqual(new["seq"], 1)
                gate.set()
                await asyncio.sleep(.1)
                self.assertIsNone(bridge.last_prediction)
                self.assertEqual(len(bridge.window), 1)
        finally:
            gate.set()

    async def test_missing_model_still_streams_sensors(self):
        def unavailable():
            raise ImportError("test TensorFlow unavailable")

        bridge, writer = await self.start_bridge(predictor_factory=unavailable)
        async with self.connect(self.uri(bridge)) as ws:
            writer.write(line(0))
            await writer.drain()
            sensor = await receive_until(ws, lambda p: p["type"] == "sensor")
            self.assertEqual(sensor["seq"], 1)
            self.assertEqual(bridge.status()["ai_state"], "error")
            self.assertIn("TensorFlow", bridge.status()["message"])

    async def test_invalid_stream_times_out_and_reconnects(self):
        bridge, writer = await self.start_bridge(read_timeout=.15)
        first_session = bridge.session_id
        writer.write(b"DATA,bad\n" * 10)
        await writer.drain()
        await asyncio.wait_for(self.connections.get(), 2)
        await asyncio.sleep(.02)
        self.assertNotEqual(bridge.session_id, first_session)
        self.assertEqual(len(bridge.window), 0)


if __name__ == "__main__":
    unittest.main()

"""Collection recovery tests: incomplete movement windows must never reach CSV."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage import collect_sequence
from SmartSignLanguage.collect_v2 import SampleStream
from SmartSignLanguage.sensor_pipeline import (
    ImuProcessor, RAW_COLUMNS, SamplingGap, make_imu_reference,
)


def raw():
    return dict(zip(RAW_COLUMNS, (1000, 1100, 0, 0, 9.81, 0, 0, 0)))


def rest_rows():
    return [{"timestamp": stamp, **raw()} for stamp in range(0, 2040, 40)]


def derived_rows(start=0, count=76):
    processor = ImuProcessor(make_imu_reference(rest_rows()))
    for stamp in range(start, start + 2040, 40):
        processor.process(stamp, raw())
    return [processor.process(stamp, raw())
            for stamp in range(start + 2040, start + 2040 + count * 40, 40)]


def send_samples(device, stamps):
    device.sendall(b"".join(
        f"RAW2,{stamp},1000,1100,0,0,9.81,0,0,0\n".encode()
        for stamp in stamps
    ))


class SequenceRecoveryTests(unittest.TestCase):
    def open_stream(self):
        client, device = socket.socketpair()
        device.settimeout(1)
        stream = SampleStream(client)
        self.addCleanup(device.close)
        self.addCleanup(stream.close)
        self.assertEqual(device.recv(100), b"RAW2\n")
        stream.configure_imu(make_imu_reference(rest_rows()))
        send_samples(device, range(0, 2160, 40))
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(
                lambda: stream.serial == 54 or stream.error is not None, timeout=2))
        self.assertIsNone(stream.error)
        self.assertTrue(stream.processor.ready)
        return stream, device

    def test_gap_while_waiting_at_menu_is_reported_as_recoverable(self):
        stream, device = self.open_stream()
        send_samples(device, [2360])  # Last timestamp 2120: 240-ms forward gap.
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(
                lambda: stream.error is not None, timeout=2))
        with self.assertRaises(SamplingGap) as caught:
            stream.check_ready()
        self.assertEqual(caught.exception.gap_ms, 240)
        self.assertIs(caught.exception, stream.error)
        self.assertFalse(stream.processor.ready)

    def test_mid_trial_gap_rejects_whole_trial_and_preserves_completed_csv(self):
        stream, device = self.open_stream()
        entered_wait = threading.Event()
        original_wait = stream.condition.wait

        def capture_wait(timeout=None):
            entered_wait.set()
            return original_wait(timeout)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "samples.csv"
            collect_sequence.save_trial(path, derived_rows(), "U01", "first", 1,
                                        "NGHIENG_GAP_DUOI")
            original_csv = path.read_bytes()

            def capture_and_save():
                rows = stream.capture(3)
                collect_sequence.save_trial(path, rows, "U01", "first", 2,
                                            "NGHIENG_GAP_DUOI")

            with patch.object(stream.condition, "wait", side_effect=capture_wait):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(capture_and_save)
                    self.assertTrue(entered_wait.wait(2))
                    send_samples(device, [*range(2160, 2600, 40), 3000])
                    with self.assertRaises(SamplingGap) as caught:
                        future.result(timeout=2)
            self.assertEqual(caught.exception.gap_ms, 440)
            self.assertEqual(path.read_bytes(), original_csv)

    def test_backward_timestamp_remains_fatal_not_recoverable_gap(self):
        stream, device = self.open_stream()
        send_samples(device, [40])
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(
                lambda: stream.error is not None, timeout=2))
        with self.assertRaisesRegex(ValueError, "timestamp quay nguoc") as caught:
            stream.capture(3)
        self.assertNotIsInstance(caught.exception, SamplingGap)

    def test_main_reconnects_and_saves_separate_sessions_after_gap(self):
        first_socket, second_socket = Mock(), Mock()
        first_stream, second_stream = Mock(), Mock()
        first_trial, second_trial = derived_rows(10000), derived_rows(20000)
        for stream, sock in ((first_stream, first_socket), (second_stream, second_socket)):
            stream.sock = sock
            stream.processor = SimpleNamespace(ready=True)
            stream.check_ready.return_value = {"hz": 25.0}
        first_stream.capture.side_effect = [rest_rows(), derived_rows(count=54),
                                           first_trial, SamplingGap(200)]
        second_stream.capture.side_effect = [rest_rows(), derived_rows(count=54),
                                            second_trial]
        answers = iter(["", "", "", "", "", "", "Q"])
        snapshot = {}

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def respond(prompt):
                if "thu lai voi phien moi" in prompt:
                    saved_paths = list(root.glob("*/samples.csv"))
                    self.assertEqual(len(saved_paths), 1)
                    snapshot[saved_paths[0]] = saved_paths[0].read_bytes()
                    first_stream.close.assert_called_once()
                return next(answers)

            with patch.object(collect_sequence.socket, "create_connection",
                              side_effect=[first_socket, second_socket]) as connect, \
                    patch.object(collect_sequence, "SampleStream",
                                 side_effect=[first_stream, second_stream]), \
                    patch.object(collect_sequence, "countdown"), \
                    patch("builtins.input", side_effect=respond), \
                    patch("sys.stdout", new_callable=io.StringIO):
                result = collect_sequence.main([
                    "--user-id", "U01", "--seconds", "3", "--output-dir", str(root)
                ])

            self.assertEqual(result, 0)
            self.assertEqual(connect.call_count, 2)
            first_stream.close.assert_called_once()
            second_stream.close.assert_called_once()
            first_stream.configure_imu.assert_called_once()
            second_stream.configure_imu.assert_called_once()
            self.assertEqual(first_stream.sock.sendall.call_count, 4)
            self.assertEqual(second_stream.sock.sendall.call_count, 2)
            self.assertEqual(len(snapshot), 1)
            for old_path, contents in snapshot.items():
                self.assertEqual(old_path.read_bytes(), contents)
            paths = list(root.glob("*/samples.csv"))
            self.assertEqual(len(paths), 2)
            session_ids = set()
            starting_timestamps = set()
            for path in paths:
                with path.open(newline="", encoding="utf-8") as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 76)
                self.assertEqual({row["trial_id"] for row in rows}, {"1"})
                self.assertEqual({row["label"] for row in rows}, {"NGHIENG_GAP_DUOI"})
                self.assertEqual({row["session_id"] for row in rows}, {path.parent.name})
                metadata = json.loads((path.parent / "imu_reference.json").read_text())
                self.assertEqual(metadata["session_id"], path.parent.name)
                session_ids.add(path.parent.name)
                starting_timestamps.add(int(rows[0]["timestamp"]))
            self.assertEqual(len(session_ids), 2)
            self.assertEqual(starting_timestamps, {12040, 22040})


if __name__ == "__main__":
    unittest.main()

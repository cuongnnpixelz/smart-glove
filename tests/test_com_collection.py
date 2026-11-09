"""COM framing and recovery must never turn interrupted trials into training rows."""
import csv
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage import collect_sequence_5 as collector
from SmartSignLanguage import collect_sequence_com as com
from SmartSignLanguage.collect_v2 import SampleStream
from SmartSignLanguage.serial_transport import SerialTransport
from SmartSignLanguage.sensor_pipeline import SamplingGap
from test_five_finger import reference, rows, raw


class ComCollectionTests(unittest.TestCase):
    def test_serial_handshake_handles_boot_noise_and_split_ack(self):
        port = Mock()
        port.in_waiting = 100
        port.read.side_effect = [b"boot\nREA", b"DY_COM5_100\n"]
        port.write.side_effect = lambda data: len(data)
        with patch("serial.Serial", return_value=port) as factory:
            transport = SerialTransport("COM8")
        factory.assert_called_once_with("COM8", 230400, timeout=.2, write_timeout=1)
        transport.settimeout(.25)
        self.assertEqual(port.timeout, .25)
        port.read.side_effect = [b"", b"RAW5_100,"]
        with self.assertRaises(socket.timeout):
            transport.recv(4096)
        self.assertEqual(transport.recv(4096), b"RAW5_100,")
        port.read.assert_called_with(100)
        transport.shutdown(2)
        port.write.assert_called_with(b"IDLE\n")
        transport.close()
        port.close.assert_called_once()

    def test_failed_handshake_closes_port_and_partial_command_is_error(self):
        port = Mock(in_waiting=100)
        port.read.return_value = b"ERROR_COM5_MPU6050\n"
        port.write.side_effect = lambda data: len(data)
        with patch("serial.Serial", return_value=port), self.assertRaisesRegex(ValueError, "MPU6050"):
            SerialTransport("COM8")
        port.close.assert_called_once()
        transport = SerialTransport.__new__(SerialTransport)
        transport.port = port
        transport._write_lock = threading.Lock()
        port.write.side_effect = None
        port.write.return_value = 1
        with self.assertRaises(OSError):
            transport.sendall(b"START\n")

    def test_heartbeat_keeps_usb_owned_during_prompts_and_stops_before_idle(self):
        port = Mock(in_waiting=100)
        port.read.return_value = b"READY_COM5_100\n"
        ping = threading.Event()

        def write(data):
            if data == b"PING\n":
                ping.set()
            return len(data)

        port.write.side_effect = write
        with patch("serial.Serial", return_value=port):
            transport = SerialTransport("COM8")
        try:
            self.assertTrue(ping.wait(2.5))
            transport.shutdown(2)
            self.assertFalse(transport._heartbeat_thread.is_alive())
            port.write.assert_called_with(b"IDLE\n")
        finally:
            transport.close()

    def test_trial_preview_and_csv_include_label_five_flex_and_imu(self):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            collector.preview_trial(rows(), "B", 4)
        message = output.getvalue()
        for expected in ("nhan=B", "trial=4", "150 mau", "100.00 Hz", "F1=", "F5=", "ACCx=", "GYRz="):
            self.assertIn(expected, message)

    def open_stream(self):
        client, device = socket.socketpair()
        device.settimeout(2)
        stream = SampleStream(client, 5, 10, recover_collection_gaps=True)
        self.addCleanup(device.close)
        self.addCleanup(stream.close)
        self.assertEqual(device.recv(100), b"RAW5_100\n")
        stream.configure_imu(reference())
        return stream, device

    def send(self, stream, device, stamps):
        before = stream.serial
        device.sendall(b"".join(
            f"RAW5_100,{s},1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n".encode()
            for s in stamps))
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(
                lambda: stream.error or stream.serial >= before + len(stamps), timeout=2))

    def test_132ms_gap_blocks_capture_but_reader_survives_and_reseed_discards_backlog(self):
        stream, device = self.open_stream()
        self.send(stream, device, [0, 10, 142, 152])
        self.assertIsNone(stream.error)
        self.assertEqual(stream.recovery_required.gap_ms, 132)
        self.assertTrue(stream.thread.is_alive())
        with self.assertRaises(SamplingGap):
            stream.capture(.1)
        with self.assertRaises(SamplingGap):
            stream.start_trial()
        stream.configure_imu(reference())
        self.assertFalse(stream.rows)
        cursor = stream.serial
        self.send(stream, device, list(range(200, 2310, 10)))
        self.assertTrue(stream.processor.ready)
        self.assertIsNone(stream.recovery_required)
        captured = stream.capture(1.5, sample_count=150, after=cursor)
        self.assertEqual(captured[0]["timestamp"], 200)
        self.assertEqual(len(captured), 150)
        self.assertTrue(all("Qw" in row for row in captured))

    def test_clock_reset_is_still_fatal(self):
        stream, device = self.open_stream()
        self.send(stream, device, [100, 110, 0])
        self.assertIsNotNone(stream.error)
        self.assertIsNone(stream.recovery_required)
        with self.assertRaisesRegex(ValueError, "timestamp"):
            stream.capture(.1)

    def test_corrupt_bytes_discard_entire_line_and_block_capture_until_reseed(self):
        stream, device = self.open_stream()
        self.send(stream, device, [0, 10])
        damaged = b'RAW5_100,20,1000,1100,1200,1300,1400,0,0,9.81' + b'\xff'*64
        device.sendall(damaged + b'RAW5_100,30,1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n')
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(lambda: stream.recovery_required or stream.error, 2))
        self.assertIsNone(stream.error)
        self.assertIsNone(stream.processor)
        self.assertEqual(stream.serial, 2)
        with self.assertRaisesRegex(ValueError, 'ASCII'):
            stream.capture(.1)
        self.send(stream, device, [40, 50])
        self.assertTrue(stream.thread.is_alive())
        with self.assertRaises(ValueError):
            stream.start_trial()
        stream.configure_imu(reference())
        cursor = stream.serial
        self.send(stream, device, list(range(60, 2170, 10)))
        batch = stream.capture(1.5, sample_count=150, after=cursor)
        self.assertEqual(batch[0]['timestamp'], 60)
        self.assertTrue(all('Qw' in row for row in batch))

    def test_repeated_corruption_stops_instead_of_hiding_bad_connection(self):
        stream, device = self.open_stream()
        device.sendall(b'RAW5_100,\xff\n'*3)
        with stream.condition:
            self.assertTrue(stream.condition.wait_for(lambda: stream.error, 2))
        with self.assertRaisesRegex(ValueError, '3 goi hong'):
            stream.capture(.1)

    def test_mid_trial_gap_retries_same_trial_and_saves_only_complete_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            args = collector.build_parser().parse_args([
                "--user-id", "U01", "--serial-port", "COM8", "--labels", "A",
                "--repetitions", "2", "--output-dir", directory])
            stream = Mock(error=None, recovery_required=None)
            stream.check_ready.return_value = {"hz": 100}
            calls = 0

            def capture(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    stream.recovery_required = SamplingGap(132)
                    raise stream.recovery_required
                return rows(start=0 if calls == 1 else 5000)

            def recover(*args):
                stream.recovery_required = None
                return True

            stream.capture.side_effect = capture
            with patch.object(collector, "SerialTransport") as transport, \
                    patch.object(collector, "SampleStream", return_value=stream), \
                    patch.object(collector, "calibrate", return_value=reference()), \
                    patch.object(collector, "countdown"), \
                    patch.object(collector, "prompt", return_value=""), \
                    patch.object(collector, "recover_imu", side_effect=recover) as recovery, \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(collector.collect_session(args), 0)
            transport.assert_called_once_with("COM8")
            recovery.assert_called_once()
            self.assertEqual(recovery.call_args.args[-1], 2)
            folder = next(Path(directory).rglob("a.csv")).parent
            with (folder/"a.csv").open() as file:
                saved = list(csv.DictReader(file))
            self.assertEqual(len(saved), 300)
            self.assertEqual({r["trial_id"] for r in saved}, {"1", "2"})
            self.assertEqual(saved[0]["timestamp"], "0")
            self.assertEqual(saved[150]["timestamp"], "5000")
            self.assertEqual(set(saved[0]), set(collector.CSV_COLUMNS))
            self.assertEqual(saved[0]["label"], "A")
            self.assertEqual(saved[0]["user_id"], "U01")
            self.assertEqual([float(saved[0][f"flex_{i}"]) for i in range(1, 6)],
                             [1000, 1100, 1200, 1300, 1400])
            self.assertEqual(json.loads((folder/"imu_reference.json").read_text())["transport"], "usb-serial")
            self.assertEqual(stream.start_trial.call_count, 3)
            stream.close.assert_called_once()

    def test_recovery_keeps_bias_and_logs_new_orientation_origin(self):
        ref = reference()
        before = json.dumps(ref, sort_keys=True)
        stream = Mock(error=None)
        stream.capture.return_value = [dict(timestamp=i*10, **raw()) for i in range(211)]
        stream.processor.ready = True
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(collector, "prompt", return_value=""), \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertTrue(collector.recover_imu(stream, ref, Path(directory), 7))
            event = json.loads((Path(directory)/"imu_recovery.jsonl").read_text())
        self.assertEqual(event["before_trial_id"], 7)
        self.assertEqual(before, json.dumps(ref, sort_keys=True))

    def test_port_listing_never_opens_device(self):
        with patch.object(com, "list_ports", return_value=[Mock(device="COM8", description="ESP32")]), \
                patch.object(com.collector, "main") as collect, \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(com.main(["--list-ports"]), 0)
        collect.assert_not_called()

    def test_interactive_words_share_calibration_and_append_repeated_label(self):
        with tempfile.TemporaryDirectory() as directory:
            args = collector.build_parser().parse_args([
                "--user-id", "U01", "--serial-port", "COM3", "--interactive-labels",
                "--repetitions", "1", "--output-dir", directory])
            stream = Mock(error=None, recovery_required=None)
            stream.check_ready.return_value = {"hz": 100}
            stream.capture.side_effect = [rows(start=i*2000) for i in range(4)]
            with patch.object(collector, "SerialTransport"), \
                    patch.object(collector, "SampleStream", return_value=stream), \
                    patch.object(collector, "calibrate", return_value=reference()) as calibration, \
                    patch.object(collector, "countdown"), \
                    patch("builtins.input", side_effect=[
                        "cảm ơn", "D", "", "", "tôi", "T", "", "",
                        "cảm ơn", "", "", "NONE", "", "", "/Q"]), \
                    patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(collector.collect_session(args), 0)
            calibration.assert_called_once()
            folder = next(Path(directory).rglob("cam_on.csv")).parent
            self.assertEqual({p.name for p in folder.iterdir()},
                             {"cam_on.csv", "toi.csv", "none.csv", "imu_reference.json"})
            with (folder/"cam_on.csv").open() as file:
                saved = list(csv.DictReader(file))
            self.assertEqual(len(saved), 300)
            self.assertEqual({r["trial_id"] for r in saved}, {"1", "3"})
            ref = json.loads((folder/"imu_reference.json").read_text())
            self.assertEqual(ref["labels"], ["CAM_ON", "TOI", "NONE"])
            self.assertEqual(ref["gesture_types"],
                             {"CAM_ON": "dynamic", "TOI": "static", "NONE": "background"})

    def test_word_normalization_rejects_unsafe_and_reserved_names(self):
        self.assertEqual(collector.normalize_word("  đồng   ý "), "DONG_Y")
        for word in ("../a", "CON", "samples", "", "a/b"):
            with self.assertRaises(ValueError):
                collector.normalize_word(word)


if __name__ == "__main__":
    unittest.main()

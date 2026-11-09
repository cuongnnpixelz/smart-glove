"""Exercise the shared firmware recording protocol over real local sockets."""
from concurrent.futures import ThreadPoolExecutor
import csv
from pathlib import Path
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "SmartSignLanguage"))
from collect_sentence_wifi import COLUMNS, CollectorError, TrialRecorder, append_trial


def sensor(stamp):
    return f"DATA,{stamp},934,1061,-3,0,0,0.33,-0.34,-0.012,9.208,-0.029,0.056,0.008\n".encode()


class CollectorSocketTests(unittest.TestCase):
    def setUp(self):
        client, self.device = socket.socketpair()
        self.device.settimeout(2)
        self.recorder = TrialRecorder(client, timeout=0.8)
        self.executor = ThreadPoolExecutor(max_workers=1)

    def tearDown(self):
        self.recorder.close()
        self.device.close()
        self.executor.shutdown(wait=True)

    def begin(self):
        pending = self.executor.submit(self.recorder.start_trial)
        self.assertEqual(self.device.recv(64), b"START\n")
        self.device.sendall(sensor(900) + b"BE")
        self.device.sendall(b"GIN\r\n")
        pending.result(timeout=2)

    def finish(self, data=b"END\n"):
        pending = self.executor.submit(self.recorder.stop_trial)
        self.assertEqual(self.device.recv(64), b"STOP\n")
        self.device.sendall(data)
        return pending.result(timeout=2)

    def test_fragmented_markers_coalesced_samples_and_trial_relative_time(self):
        self.begin()
        self.device.sendall(sensor(1000) + sensor(1040))
        samples = self.finish(sensor(1080) + b"END\n" + sensor(1120))
        self.assertEqual([row[0] for row in samples], [0, 40, 80])
        self.assertEqual(samples[0][1:3], (934.0, 1061.0))
        self.assertEqual(len(samples[0]), 13)
        self.begin()
        self.device.sendall(sensor(2000))
        second = self.finish(sensor(2040) + b"END\n")
        self.assertEqual([row[0] for row in second], [0, 40])

    def test_disconnect_rejects_partial_trial(self):
        self.begin()
        self.device.sendall(sensor(1000))
        self.device.close()
        self.assertTrue(self.recorder._ended.wait(2))
        with self.assertRaises(CollectorError):
            self.recorder.stop_trial()

    def test_sensor_reset_rejects_trial(self):
        self.begin()
        self.device.sendall(sensor(1000) + sensor(0))
        self.assertTrue(self.recorder._ended.wait(2))
        with self.assertRaisesRegex(CollectorError, "reset"):
            self.recorder.stop_trial()

    def test_nonfinite_sensor_rejects_trial(self):
        self.begin()
        self.device.sendall(sensor(1000).replace(b"934", b"nan"))
        self.assertTrue(self.recorder._ended.wait(2))
        with self.assertRaisesRegex(CollectorError, "dinh dang"):
            self.recorder.stop_trial()

    def test_missing_begin_times_out_instead_of_hanging(self):
        pending = self.executor.submit(self.recorder.start_trial)
        self.assertEqual(self.device.recv(64), b"START\n")
        with self.assertRaises(CollectorError):
            pending.result(timeout=2)

    def test_open_socket_without_samples_is_detected(self):
        self.begin()
        self.assertTrue(self.recorder._ended.wait(2))
        with self.assertRaisesRegex(CollectorError, "khong gui"):
            self.recorder.stop_trial()


class CollectorCsvTests(unittest.TestCase):
    def test_append_preserves_existing_trials_and_header(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trials.csv"
            samples = [(0, *range(12)), (40, *range(12))]
            self.assertEqual(append_trial(target, "XIN_CHAO", samples), 1)
            original = target.read_bytes()
            self.assertEqual(append_trial(target, "NONE", samples), 2)
            self.assertTrue(target.read_bytes().startswith(original))
            with target.open(newline="", encoding="utf-8") as source:
                rows = list(csv.reader(source))
            self.assertEqual(rows[0], COLUMNS)
            self.assertEqual(len(rows), 5)

    def test_rejects_incompatible_csv_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trials.csv"
            target.write_text("wrong,header\n", encoding="utf-8")
            original = target.read_bytes()
            with self.assertRaises(CollectorError):
                append_trial(target, "XIN_CHAO", [(0, *range(12))])
            self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

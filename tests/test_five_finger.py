"""Synthetic protocol/training checks, not evidence of real gesture accuracy."""
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np

from SmartSignLanguage.five_finger import CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS, parse_raw5
from SmartSignLanguage.collect_v2 import SampleStream
from SmartSignLanguage.collect_sequence import save_trial
from SmartSignLanguage.collect_sequence_5 import build_parser, calibrate
from SmartSignLanguage.five_finger import CALIBRATION_SCHEMA, trial_quality, make_flex_calibration, make_finger_calibration
from SmartSignLanguage.sensor_pipeline import ImuProcessor, make_imu_reference
from SmartSignLanguage import sequence_model_5 as backend
from SmartSignLanguage.train_sequence import load_trials
from SmartSignLanguage.train_sequence_5 import main as train


def raw():
    return dict(zip(FLEX_COLUMNS, [1000, 1100, 1200, 1300, 1400]),
                ACCx=0, ACCy=0, ACCz=9.81, GYRx=0, GYRy=0, GYRz=0)


def reference(sid="s1"):
    ref = make_imu_reference([dict(timestamp=i*10, **raw()) for i in range(201)], sample_ms=10)
    ref.update(session_id=sid, user_id="U01", trial_seconds=1.5, flex_calibration_schema=CALIBRATION_SCHEMA,
               divider_ohms=10000, supply_volts=3.3, divider_topology="3V3-flex-ADC-10k-GND",
               flex_calibration={k: {"open": raw()[k], "closed": raw()[k]-400, "noise_p90": 0,
                                    "open_p05": raw()[k], "open_p95": raw()[k],
                                    "closed_p05": raw()[k]-400, "closed_p95": raw()[k]-400,
                                    "open_drift": 0, "closed_drift": 0} for k in FLEX_COLUMNS},
               flex_pins=FLEX_PINS, fingers=FINGERS, csv_columns=list(CSV_COLUMNS))
    return ref


def rows(start=0, finger=None, static=False):
    processor = ImuProcessor(reference())
    result = []
    for i in range(150):
        sample = raw()
        if finger is not None:
            sample[FLEX_COLUMNS[finger]] -= 400 if static else max(0, 1-abs(i-75)/35)*200
        result.append({**sample, **processor.process(start+i*10, sample)})
    return result


class FiveFingerTests(unittest.TestCase):
    def test_raw5_channel_order_and_invalid_packets(self):
        line = b"RAW5,40,1000,1100,1200,1300,1400,1,2,3,4,5,6\n"
        stamp, sample = parse_raw5(line)
        self.assertEqual(stamp, 40)
        self.assertEqual([sample[k] for k in FLEX_COLUMNS], [1000,1100,1200,1300,1400])
        self.assertEqual([sample[k] for k in ("ACCx","ACCy","ACCz","GYRx","GYRy","GYRz")], [1,2,3,4,5,6])
        for bad in (line.replace(b"RAW5", b"RAW2"), line.replace(b"1400", b"4096"),
                    line.replace(b"1200", b"nan"), line.replace(b"1300", b"-1"),
                    line.replace(b",40,", b",4294967296,"), line+b",0", b"RAW5,\xff"):
            self.assertIsNone(parse_raw5(bad))

    def test_fragmented_stream_preserves_extra_fingers_after_imu(self):
        client, server = socket.socketpair()
        stream = SampleStream(client, flex_count=5, sample_ms=10)
        self.assertEqual(server.recv(20), b"RAW5_100\n")
        stream.configure_imu(reference())
        stopped = threading.Event()

        def send():
            try:
                for i in range(200):
                    packet = f"RAW5_100,{i*10},1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n".encode()
                    server.sendall(packet[:17])
                    server.sendall(packet[17:])
                    if stopped.wait(.003):
                        break
            except OSError:
                pass

        thread = threading.Thread(target=send)
        thread.start()
        try:
            captured = stream.capture(1.5, sample_count=150)
            self.assertEqual(len(captured), 150)
            for row in captured:
                self.assertEqual([row[k] for k in FLEX_COLUMNS], [1000,1100,1200,1300,1400])
                self.assertIn("Qw", row)
                self.assertIn("ACCz_body", row)
        finally:
            stopped.set()
            thread.join(1)
            stream.close()
            server.close()

    def test_all_five_fingers_contribute_and_old_reference_rejected(self):
        baseline = backend.sequence_vector(rows(), reference()).reshape(150, -1)
        self.assertEqual(baseline.shape, (150, 19))
        for finger in range(5):
            x = backend.sequence_vector(rows(finger=finger), reference()).reshape(150, -1)
            self.assertGreater(np.ptp(x[:, finger]), .4)
            self.assertGreater(np.ptp(x[:, 14+finger]), 1)
            others = [i for i in range(5) if i != finger]
            np.testing.assert_array_equal(x[:, others], baseline[:, others])
        old = reference()
        del old["flex_pins"]
        with self.assertRaises(ValueError):
            backend.sequence_vector(rows(), old)
        for batch in (rows()[:50], rows()[:10]+rows()[15:]):
            with self.assertRaises(ValueError):
                backend.sequence_vector(batch, reference())

    def test_static_pose_is_not_erased_and_calibration_removes_session_offset(self):
        for finger in range(5):
            batch = rows(finger=finger, static=True)
            x = backend.sequence_vector(batch, reference()).reshape(150, -1)
            np.testing.assert_allclose(x[:, finger], 1)
            np.testing.assert_allclose(x[:, 14:19], 0)
            shifted = [{**r, **{k:r[k]+150 for k in FLEX_COLUMNS}} for r in batch]
            ref = reference()
            for c in ref["flex_calibration"].values():
                for field in ("open", "closed", "open_p05", "open_p95", "closed_p05", "closed_p95"):
                    c[field] += 150
            np.testing.assert_allclose(backend.sequence_vector(shifted, ref), x.reshape(-1))

    def test_begin_boundary_excludes_backlog_and_keeps_exactly_150_samples(self):
        client, server = socket.socketpair()
        stream = SampleStream(client, flex_count=5, sample_ms=10)
        self.assertEqual(server.recv(40), b"RAW5_100\n")
        done = threading.Event()

        def device():
            server.sendall(b"RAW5_100,900,1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n")
            self.assertEqual(server.recv(40), b"START\n")
            payload = b"BEGIN\n" + b"".join(
                f"RAW5_100,{1000+i*10},1000,1100,1200,1300,1400,0,0,9.81,0,0,0\n".encode()
                for i in range(155))
            server.sendall(payload[:9])
            server.sendall(payload[9:])
            done.wait(2)

        thread = threading.Thread(target=device)
        thread.start()
        try:
            cursor = stream.start_trial()
            batch = stream.capture(1.5, sample_count=150, after=cursor)
            self.assertEqual(len(batch), 150)
            self.assertEqual(batch[0]["timestamp"], 1000)
            self.assertEqual(batch[-1]["timestamp"], 2490)
            self.assertEqual(trial_quality(batch)["hz"], 100)
        finally:
            done.set()
            thread.join(2)
            stream.close()
            server.close()

    def test_calibration_rejects_disconnected_reversed_and_noisy_flex(self):
        opened = [dict(timestamp=i*10, **raw()) for i in range(201)]
        closed = [{**r, **{k:r[k]-400 for k in FLEX_COLUMNS}} for r in opened]
        self.assertEqual(make_flex_calibration(opened, closed)["flex_5"]["closed"], 1000)
        for bad_value in (0, 4095, 1450, 1390):
            bad = [dict(r, flex_5=bad_value) for r in closed]
            with self.assertRaises(ValueError):
                make_flex_calibration(opened, bad)
        noisy = [dict(r, flex_5=1000+(450 if i%2 else -450)) for i,r in enumerate(closed)]
        with self.assertRaises(ValueError):
            make_flex_calibration(opened, noisy)

    def test_unchanged_pose_with_noise_reports_zero_response(self):
        same = [dict(timestamp=i*10, **{**raw(), "flex_1": 1028.5+(15 if i%2 else 0)})
                for i in range(201)]
        with self.assertRaisesRegex(ValueError, r"bien do=0.0, dao dong P90=15.0"):
            make_finger_calibration(same, same, "flex_1")

    def test_small_but_separated_signal_is_accepted_by_collection_and_training(self):
        opened = [dict(timestamp=i*10, **{**raw(), "flex_1": 1007+(i%20-9.5)*11/19})
                  for i in range(201)]
        closed = [dict(r, flex_1=r["flex_1"]-25) for r in opened]
        c = make_finger_calibration(opened, closed, "flex_1")
        self.assertAlmostEqual(c["open"]-c["closed"], 25)
        ref = reference()
        ref["flex_calibration"]["flex_1"] = c
        backend.validate_reference(ref)
        self.assertEqual(len(backend.sequence_vector(rows(), ref)), 150*19)
        malformed = reference()
        malformed["flex_calibration"]["flex_1"] = dict(c)
        del malformed["flex_calibration"]["flex_1"]["open_p05"]
        with self.assertRaises(ValueError):
            backend.validate_reference(malformed)
        overlapping = [dict(r, flex_1=r["flex_1"]-3) for r in opened]
        with self.assertRaises(ValueError):
            make_finger_calibration(opened, overlapping, "flex_1")

    def test_overlapping_ranges_and_pose_drift_are_rejected(self):
        opened = [dict(timestamp=i*10, **{**raw(), "flex_1": 1000+(i%20-9.5)*40/19})
                  for i in range(201)]
        closed = [dict(r, flex_1=r["flex_1"]-25) for r in opened]
        with self.assertRaisesRegex(ValueError, "chong lan"):
            make_finger_calibration(opened, closed, "flex_1")
        stable = [dict(r, flex_1=1000) for r in opened]
        drifting = [dict(r, flex_1=900-i*.2) for i,r in enumerate(opened)]
        with self.assertRaisesRegex(ValueError, "troi"):
            make_finger_calibration(stable, drifting, "flex_1")

    def test_legacy_calibration_remains_readable(self):
        ref = reference()
        ref["flex_calibration_schema"] = "five-flex-10k-calibration-v1"
        for key in FLEX_COLUMNS:
            ref["flex_calibration"][key] = {"open": raw()[key], "closed": raw()[key]-400, "noise_p90": 0}
        backend.validate_reference(ref)

    def test_all_fingers_calibration_rejects_bad_thumb_then_retries_two_poses(self):
        opened = [dict(timestamp=i*10, **raw()) for i in range(201)]
        closed = [{**r, **{k:r[k]-400 for k in FLEX_COLUMNS}} for r in opened]
        bad_closed = [{**r, 'flex_1': opened[i]['flex_1']} for i, r in enumerate(closed)]
        poses = [opened, bad_closed, opened, closed, opened]
        stream = Mock()
        stream.processor.ready = True
        with patch("SmartSignLanguage.collect_sequence_5.prompt", return_value=""), \
                patch("SmartSignLanguage.collect_sequence_5.countdown"), \
                patch("SmartSignLanguage.collect_sequence_5.capture_stable_pose", side_effect=poses) as capture, \
                patch("sys.stdout", new_callable=io.StringIO):
            ref = calibrate(stream)
        self.assertEqual(capture.call_count, 5)
        for k in FLEX_COLUMNS:
            self.assertEqual(ref["flex_calibration"][k]["open"]-ref["flex_calibration"][k]["closed"], 400)
        self.assertEqual(ref["flex_calibration_method"], "all-fingers-3s-last-2s")

    def test_all_fingers_calibration_needs_only_two_flex_poses_and_one_imu_pose(self):
        opened = [dict(timestamp=i*10, **raw()) for i in range(201)]
        closed = [{**r, **{k:r[k]-400 for k in FLEX_COLUMNS}} for r in opened]
        stream = Mock()
        stream.processor.ready = True
        with patch("SmartSignLanguage.collect_sequence_5.prompt", return_value="") as ask, \
                patch("SmartSignLanguage.collect_sequence_5.countdown"), \
                patch("SmartSignLanguage.collect_sequence_5.capture_stable_pose", side_effect=[opened, closed, opened]) as capture, \
                patch("sys.stdout", new_callable=io.StringIO):
            ref = calibrate(stream)
        self.assertEqual(capture.call_count, 3)
        self.assertEqual(ask.call_count, 3)
        self.assertEqual(set(ref['flex_calibration']), set(FLEX_COLUMNS))

    def test_wrong_rate_legacy_reference_and_clipping_rejected(self):
        for bad in ([dict(r, timestamp=i*40) for i,r in enumerate(rows())],
                    [dict(r, flex_3=4095) for r in rows()],
                    [dict(r, GYRx=4.35) for r in rows()]):
            with self.assertRaises(ValueError):
                backend.sequence_vector(bad, reference())
        ref = reference()
        ref["sample_ms"] = 40
        with self.assertRaises(ValueError):
            backend.sequence_vector(rows(), ref)

    def test_collection_defaults_and_training_roundtrip(self):
        args = build_parser().parse_args(["--user-id", "U01"])
        self.assertEqual(args.repetitions, 10)
        self.assertEqual(args.labels, ["A", "B", "C", "D", "NONE"])
        self.assertEqual(args.output_dir.name, "sequence_data_5_100hz")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/"data"
            for sid in ("s1", "s2"):
                folder = root/sid
                folder.mkdir(parents=True)
                (folder/"imu_reference.json").write_text(json.dumps(reference(sid)))
                for tid in range(1, 9):
                    gesture = tid % 2 == 0
                    save_trial(folder/"samples.csv", rows(tid*6000, 4 if gesture else None, static=True),
                               "U01", sid, tid, "MOVE" if gesture else "NONE", columns=CSV_COLUMNS, quality_check=trial_quality)
            output = Path(d)/"model"
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(train(["--data", str(root), "--output", str(output)]), 0)
                self.assertEqual(train(["--data", str(root), "--output", str(output)]), 1)
            saved = backend.SequenceModel(output)
            self.assertEqual(saved.predict(rows(finger=4, static=True), reference()), "MOVE")
            self.assertEqual(saved.predict(rows(), reference()), "NONE")
            report = json.loads((output/"report.json").read_text())
            self.assertEqual(report["evaluation_scope"], "session_holdout")
            trials, _, _ = load_trials(root, backend)
            training = [t["vector"] for t in trials if t["key"] in report["train_keys"]]
            np.testing.assert_allclose(saved.model[0].mean_, np.asarray(training, dtype=float).mean(axis=0))
            with self.assertRaisesRegex(ValueError, "wrong CSV schema"):
                load_trials(root)
            ref_path = root/"s1"/"imu_reference.json"
            bad = reference("s1")
            bad["flex_pins"] = [33,32,34,35,36]
            ref_path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                load_trials(root, backend)


if __name__ == "__main__":
    unittest.main()

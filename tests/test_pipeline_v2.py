"""Deterministic physics/protocol/data tests; synthetic values are NOT training data."""
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
import numpy as np

from SmartSignLanguage.sensor_pipeline import (
    SCHEMA, PROCESSOR, CSV_COLUMNS, Q_COLUMNS, BODY_COLUMNS, WORLD_COLUMNS,
    RAW_COLUMNS, MODEL_FEATURES, SensorProcessor, ImuProcessor, make_imu_reference, make_calibration, model_vector,
    make_window, timing_report, rotate, from_legacy)
from SmartSignLanguage.collect_v2 import SampleStream, save_trial
from SmartSignLanguage.collect_sequence import (
    COLUMNS as SEQUENCE_COLUMNS,
    save_trial as save_sequence_trial,
    valid_label,
)
from SmartSignLanguage.train_v2 import read_dataset, split_trials
from SmartSignLanguage.wifi_ai import parse_sensor_line, Bridge


def calibration(session="session1"):
    return {"schema":SCHEMA,"processor":PROCESSOR,"sample_ms":40,
            "flex_1":{"open":1000.,"closed":800.},"flex_2":{"open":1100.,"closed":900.},
            "gyro_bias":[0.,0.,0.],"gravity":9.81,"flex1_finger":"Index",
            "session_id":session,"user_id":"test"}


def raw(f1=1000,f2=1100,acc=(0,0,9.81),gyro=(0,0,0)):
    return dict(zip(RAW_COLUMNS,(f1,f2,*acc,*gyro)))


def rows_for_trial(c,start=0,label="NONE"):
    processor=SensorProcessor(c)
    # Warm-up the continuous filter before saving a trial, like collect_v2.
    for stamp in range(start,start+2400,40):
        processor.process(stamp,raw())
    return [processor.process(stamp,raw(f1=900 if label=="CAM_ON_NHIEU" else 1000,
                                       f2=1000 if label=="XIN_CHAO" else 1100))
            for stamp in range(start+2400,start+4840,40)]


class PipelineTests(unittest.TestCase):
    def test_raw_protocol_order_finite_checks_and_legacy_adapter(self):
        line=b"RAW2,400,1000,1100,0,0,9.81,0.1,0.2,0.3\n"
        stamp,f=parse_sensor_line(line)
        self.assertEqual(stamp,400)
        self.assertEqual(from_legacy(f),raw(gyro=(.1,.2,.3)))
        for invalid in (line.replace(b"9.81",b"nan"),line.replace(b"1000",b"4096"),line.replace(b",400,",b",4.5,"),line+b",0"):
            self.assertIsNone(parse_sensor_line(invalid))

    def test_calibration_handles_decreasing_adc_without_overwriting_raw(self):
        c=calibration()
        row=SensorProcessor(c).process(0,raw(900,950))
        x=model_vector(row,c)
        self.assertEqual(row["flex_1"],900)
        np.testing.assert_allclose(x[:2],[.5,.75])
        row.update(flex_1=700,flex_2=1200)
        np.testing.assert_allclose(model_vector(row,c)[:2],[1,0])

    def test_calibration_rejects_motion_and_degenerate_ranges(self):
        opened=[{"timestamp":t,**raw()} for t in range(0,2040,40)]
        closed=[{"timestamp":t,**raw(800,900)} for t in range(0,2040,40)]
        c=make_calibration(opened,closed,opened)
        self.assertEqual(c["flex_1"],{"open":1000,"closed":800})
        with self.assertRaises(ValueError):
            make_calibration(opened,opened,opened)
        unstable=[dict(r,flex_1=800+(i%2)*100) for i,r in enumerate(closed)]
        with self.assertRaisesRegex(ValueError,"not stable"):
            make_calibration(opened,unstable,opened)

    def test_stationary_tilt_gravity_and_world_rotation(self):
        for a in [(0,0,9.81),(0,9.81,0),(-9.81,0,0),(0,0,-9.81)]:
            p=SensorProcessor(calibration())
            for t in range(0,2440,40):
                row=p.process(t,raw(acc=a))
            self.assertTrue(p.ready)
            q=np.array([row[k] for k in Q_COLUMNS])
            self.assertAlmostEqual(np.linalg.norm(q),1)
            np.testing.assert_allclose([row[k] for k in BODY_COLUMNS],[0,0,0],atol=1e-7)
            np.testing.assert_allclose(rotate(q,a),[0,0,9.81],atol=1e-7)

    def test_gyro_yaw_integration_and_bias_use_seconds_and_radians(self):
        c=calibration();c["gyro_bias"]=[0,0,.01]
        p=SensorProcessor(c)
        for t in range(0,1040,40):
            row=p.process(t,raw(gyro=(0,0,np.pi/2+.01)))
        q=[row[k] for k in Q_COLUMNS]
        np.testing.assert_allclose(rotate(q,[1,0,0]),[0,1,0],atol=.002)
        self.assertAlmostEqual(float(model_vector(row,c)[4]),np.pi/2,places=6)

    def test_gap_resets_filter_and_nonfinite_is_rejected(self):
        p=SensorProcessor(calibration());p.process(0,raw())
        with self.assertRaises(ValueError):
            p.process(1000,raw())
        self.assertIsNone(p.q)
        self.assertFalse(p.ready)
        with self.assertRaises(ValueError):
            p.process(1001,raw(f1=float("nan")))

    def test_slow_or_broken_csv_timing_is_not_time_warped(self):
        for step in (0,165,400):
            with self.assertRaises(ValueError):
                timing_report([{"timestamp":i*step} for i in range(50)])
        rows=[{"timestamp":i*40} for i in range(50)]
        rows[0]["timestamp"]=-1000000
        with self.assertRaises(ValueError):
            timing_report(rows)

    def test_offline_live_windows_match_with_jitter_and_reject_short_input(self):
        c=calibration();p=SensorProcessor(c)
        stamps=[i*40+(5 if i%2 else 0) for i in range(100)]
        rows=[p.process(t,raw(f1=1000-t/40)) for t in stamps]
        offline=make_window(rows,c,end=stamps[-1])
        live=make_window(rows[-60:],c)
        self.assertEqual(offline.shape,(50,11))
        np.testing.assert_array_equal(offline,live)
        self.assertIsNone(make_window(rows[:20],c))

    def test_v2_csv_has_no_derivatives_and_validates_before_append(self):
        c=calibration();rows=rows_for_trial(c)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"samples.csv"
            save_trial(path,rows,c,1,"NONE")
            original=path.read_bytes()
            with path.open() as source:
                header=next(csv.reader(source))
            self.assertEqual(header,list(CSV_COLUMNS))
            self.assertNotIn("dFlex1",header)
            with self.assertRaises(ValueError):
                save_trial(path,rows,c,1,"NONE")
            self.assertEqual(path.read_bytes(),original)

    def test_sequence_csv_saves_derived_channels_and_preserves_raw_flex(self):
        rest = [{"timestamp": i*40, **raw(gyro=(.01, 0, 0))} for i in range(51)]
        reference = make_imu_reference(rest)
        self.assertFalse(reference["flex_calibrated"])
        self.assertNotIn("flex_1", reference)
        p = ImuProcessor(reference)
        rows = [p.process(i*40, raw(f1=900+i, f2=1000-i, gyro=(.01, 0, 0))) for i in range(76)]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sequence_data" / "session-a" / "samples.csv"
            path.parent.mkdir(parents=True)
            quality = save_sequence_trial(path, rows, "U01", "session-a", 1, "tam biet")
            self.assertAlmostEqual(quality["hz"], 25.)
            with path.open(newline="", encoding="utf-8") as source:
                saved = list(csv.DictReader(source))
            self.assertEqual(saved[0]["label"], "TAM_BIET")
            self.assertEqual(list(saved[0]), list(SEQUENCE_COLUMNS))
            self.assertNotIn("dFlex1", saved[0])
            self.assertNotIn("flex_3", saved[0])
            self.assertEqual(float(saved[0]["flex_1"]), 900)
            self.assertEqual(float(saved[0]["GYRx"]), .01)
            self.assertEqual(len(saved), 76)
            np.testing.assert_allclose([float(saved[-1][k]) for k in Q_COLUMNS], [1,0,0,0])
            np.testing.assert_allclose([float(saved[-1][k]) for k in (*BODY_COLUMNS, *WORLD_COLUMNS)], 0)
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "Trung session/trial"):
                save_sequence_trial(path, rows, "U01", "session-a", 1, "TAM_BIET")
            self.assertEqual(path.read_bytes(), original)
            for bad in ({k:v for k,v in rows[0].items() if k != "Qw"},
                        dict(rows[0], ACCx_body=float("nan")), dict(rows[0], Qw=2)):
                with self.assertRaises(ValueError):
                    save_sequence_trial(path, [bad, *rows[1:]], "U01", "session-a", 2, "NONE")
                self.assertEqual(path.read_bytes(), original)
            path.write_text("timestamp,flex_1\n0,900\n")
            old_schema = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "header khac"):
                save_sequence_trial(path, rows, "U01", "session-a", 2, "NONE")
            self.assertEqual(path.read_bytes(), old_schema)
        with self.assertRaises(ValueError):
            valid_label("nhan/co/dau")

    def test_imu_reference_rejects_motion_and_bad_stationary_data(self):
        rest = [{"timestamp": i*40, **raw()} for i in range(51)]
        for invalid in (rest[:10], [dict(r, GYRx=(i%2)*.2) for i,r in enumerate(rest)],
                        [dict(r, ACCz=0) for r in rest], [dict(r, ACCx=float("nan")) for r in rest]):
            with self.assertRaises(ValueError):
                make_imu_reference(invalid)

    def test_stream_computes_imu_continuously_and_saves_a_three_second_sequence(self):
        reference = make_imu_reference([{"timestamp": i*40, **raw()} for i in range(51)])
        client, device = socket.socketpair()
        device.settimeout(1)
        stream = SampleStream(client)
        try:
            self.assertEqual(device.recv(100), b"RAW2\n")
            stream.configure_imu(reference)
            with ThreadPoolExecutor(max_workers=1) as pool:
                def capture(seconds, stamps):
                    future = pool.submit(stream.capture, seconds)
                    time.sleep(.03)
                    for t in stamps:
                        device.sendall(f"RAW2,{t},1000,1100,0,0,9.81,0,0,0\n".encode())
                    return future.result(2)
                capture(2.1, range(0, 2161, 40))
                self.assertTrue(stream.processor.ready)
                rows = capture(3, range(2200, 5241, 40))
            self.assertGreaterEqual(rows[-1]["timestamp"]-rows[0]["timestamp"], 3000)
            with tempfile.TemporaryDirectory() as d:
                path = Path(d)/"samples.csv"
                save_sequence_trial(path, rows, "U01", "s1", 1, "NGHIENG_GAP_DUOI")
                with path.open() as source:
                    saved = list(csv.DictReader(source))
                self.assertEqual(set(r["label"] for r in saved), {"NGHIENG_GAP_DUOI"})
                self.assertTrue(all(set(Q_COLUMNS+BODY_COLUMNS+WORLD_COLUMNS) <= r.keys() for r in saved))
        finally:
            stream.close()
            device.close()

    def test_dataset_rejects_tampered_derived_physics(self):
        c=calibration();rows=rows_for_trial(c)
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/"calibration.json").write_text(json.dumps(c))
            save_trial(folder/"samples.csv",rows,c,1,"NONE")
            trials,_,_=read_dataset(folder)
            self.assertEqual(len(trials[0]["windows"]),3)
            text=(folder/"samples.csv").read_text()
            # Change the unit quaternion to a non-unit value in one row.
            (folder/"samples.csv").write_text(text.replace(",1.0,0.0,0.0,-0.0,",",2.0,0.0,0.0,-0.0,",1))
            # Use a guaranteed named-column mutation if float repr changes.
            with (folder/"samples.csv").open(newline="") as f:
                values=list(csv.DictReader(f))
            values[0]["Qw"]="2"
            with (folder/"samples.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=CSV_COLUMNS);w.writeheader();w.writerows(values)
            with self.assertRaisesRegex(ValueError,"inconsistent"):
                read_dataset(folder)

    def test_holdout_groups_are_disjoint_and_small_datasets_fail(self):
        trials=[{"session":str(s),"user":str(s),"label":label,"key":f"{s}/{label}/{i}"}
                for s in range(5) for label in ("NONE","XIN_CHAO","CAM_ON_NHIEU") for i in range(10)]
        splits,groups=split_trials(trials)
        self.assertFalse(set(groups["train"])&set(groups["test"]))
        self.assertFalse(set(groups["validation"])&set(groups["test"]))
        with self.assertRaises(ValueError):
            split_trials(trials[:30])

    def test_bridge_v2_uses_calibrated_windows_and_clears_on_gap(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"cal.json";path.write_text(json.dumps(calibration()))
            bridge=Bridge(pipeline="v2",calibration=path,predictor_factory=lambda:None)
            values=(900,1000,0,0,0,0,0,0,9.81,0,0,0)
            for stamp in range(0,2440,40):
                bridge.ingest(stamp,values)
            self.assertEqual(bridge.last_sensor["processed"]["flex_1_norm"],.5)
            self.assertNotIn("dFlex1",bridge.last_sensor["sensors"])
            _,_,_,window=bridge.jobs.get_nowait()
            self.assertEqual(window.shape,(50,11))
            old=bridge.session_id
            bridge.ingest(5000,values)
            self.assertNotEqual(bridge.session_id,old)
            self.assertEqual(len(bridge.window),1)
            self.assertTrue(bridge.jobs.empty())

    def test_stream_rejects_continuous_legacy_packets_before_collection(self):
        client, device = socket.socketpair()
        device.settimeout(1)
        stream = SampleStream(client)
        try:
            self.assertEqual(device.recv(100), b"RAW2\n")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not stream.error:
                device.sendall(b"DATA,100,1000,1100,0,0,0,0,0,0,9.81,0,0,0\n")
                time.sleep(.04)
            with self.assertRaisesRegex(ValueError, "DATA cu"):
                stream.check_ready()
            self.assertEqual(stream.serial, 0)
        finally:
            stream.close()
            device.close()

    def test_stream_drains_idle_packets_and_captures_new_raw2_only(self):
        client,device=socket.socketpair();device.settimeout(1)
        stream=SampleStream(client)
        try:
            self.assertEqual(device.recv(100),b"RAW2\n")
            device.sendall(b"RAW2,0,1000,1100,0,0,9.81,0,0,0\n")
            with stream.condition:
                stream.condition.wait_for(lambda:stream.serial==1,timeout=1)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(stream.capture,.2)
                time.sleep(.03)
                # Packet fragmentation and batched arrival must preserve device time.
                data=b"".join(f"RAW2,{t},1000,1100,0,0,9.81,0,0,0\n".encode() for t in range(40,281,40))
                device.sendall(data[:17]);device.sendall(data[17:])
                rows=future.result(2)
                self.assertEqual(rows[0]["timestamp"],40)
                self.assertGreaterEqual(rows[-1]["timestamp"]-rows[0]["timestamp"],200)
        finally:
            stream.close();device.close()


if __name__=="__main__":
    unittest.main()

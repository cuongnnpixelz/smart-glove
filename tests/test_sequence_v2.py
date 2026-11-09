"""Synthetic pipeline checks; these tests do not measure glove accuracy."""
import csv
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from SmartSignLanguage import collect_sequence, sequence_model_v2 as backend
from SmartSignLanguage.collect_sequence import save_trial
from SmartSignLanguage.sensor_pipeline import make_imu_reference, rotate
from SmartSignLanguage.sequence_motion_v2 import learn_profiles, evaluate
from SmartSignLanguage.train_sequence import load_trials
from SmartSignLanguage.train_sequence_v2 import main as train


def reference(sid="s1"):
    raw = dict(flex_1=950, flex_2=1050, ACCx=0, ACCy=0, ACCz=9.81, GYRx=0, GYRy=0, GYRz=0)
    ref = make_imu_reference([dict(raw, timestamp=i*40) for i in range(51)])
    ref.update(session_id=sid, user_id="U01", trial_seconds=5)
    return ref


def rows(mode="correct", start=0, offset=0):
    t = backend.GRID
    bend = np.interp(t, [0, 600, 1100, 3400, 4300, 5000], [0,0,1,1,.4,.4])
    tilt = np.interp(t, [0,1500,2000,2600,3100,5000], [0,0,.8,.8,0,0])
    other = bend.copy()
    if mode in ("tilt_only", "rest"):
        bend[:]=0; other[:]=0
    if mode == "one_finger":
        other[:]=0
    if mode in ("bend_only", "rest"):
        tilt[:]=0
    if mode == "wrong_direction":
        tilt *= -1
    if mode == "wrong_order":
        tilt = np.interp(t, [0,600,1000,2600,3100,5000], [0,0,.8,.8,0,0])
    if mode == "early_release":
        bend = np.interp(t, [0,600,1100,2100,2300,5000], [0,0,1,1,0,0]); other=bend.copy()
    if mode == "no_release":
        bend[t>3400]=1; other=bend.copy()
    result = []
    speed = np.gradient(tilt, .04)
    for i,(stamp,b,c,a) in enumerate(zip(t,bend,other,tilt)):
        q = np.array([np.cos(a/2), 0, np.sin(a/2), 0])
        acc = rotate(q*[1,-1,-1,-1], [0,0,9.81])
        result.append(dict(timestamp=int(start+stamp), flex_1=950+offset-80*b,
                           flex_2=1050+offset-100*c, Qw=q[0], Qx=q[1], Qy=q[2], Qz=q[3],
                           GYRx=0, GYRy=speed[i], GYRz=0, ACCx=acc[0], ACCy=acc[1], ACCz=acc[2],
                           ACCx_body=0, ACCy_body=0, ACCz_body=0, ACCx_world=0, ACCy_world=0, ACCz_world=0))
    return result


def positive_trials():
    return [dict(key=f"train/{i}", label="NGHIENG_GAP_DUOI",
                 vector=backend.sequence_vector(rows(offset=i*10), reference())) for i in range(5)]


class SequenceV2Tests(unittest.TestCase):
    def test_relative_baseline_slopes_units_and_partial_recovery(self):
        x = backend.sequence_vector(rows(), reference()).reshape(len(backend.GRID), -1)
        self.assertEqual(x.shape, (126,14))
        np.testing.assert_allclose(x, backend.sequence_vector(rows(offset=99), reference()).reshape(126,14), atol=1e-4)
        np.testing.assert_allclose(x[20,-2:], [-160,-200], atol=1e-3)
        # The end is still displaced: no artificial forcing back to zero.
        np.testing.assert_allclose(x[-1,:2], [-32,-40], atol=1e-4)
        np.testing.assert_allclose(x[-1,-2:], [0,0], atol=1e-4)

    def test_short_and_missing_windows_rejected(self):
        for batch in (rows()[:76], rows()[:20]+rows()[25:]):
            with self.assertRaises(ValueError):
                backend.sequence_vector(batch, reference())

    def test_motion_allows_partial_recovery_but_requires_both_flex_direction_order(self):
        profile = learn_profiles(positive_trials())["NGHIENG_GAP_DUOI"]
        self.assertTrue(evaluate(positive_trials()[0]["vector"], profile)[0])
        for mode in ("tilt_only", "one_finger", "bend_only", "wrong_direction", "wrong_order", "early_release", "no_release", "rest"):
            with self.subTest(mode=mode):
                self.assertFalse(evaluate(backend.sequence_vector(rows(mode), reference()), profile)[0])

    def test_uninformative_positive_flex_rejected_at_training(self):
        trials = positive_trials()
        for t in trials:
            t["vector"] = backend.sequence_vector(rows("one_finger"), reference())
        with self.assertRaisesRegex(ValueError, "CA HAI"):
            learn_profiles(trials)

    def create_data(self, root, sessions=3):
        for s in range(sessions):
            sid = f"s{s}"
            folder = root/sid
            folder.mkdir(parents=True)
            (folder/"imu_reference.json").write_text(json.dumps(reference(sid)), encoding="utf-8")
            for tid in range(1,13):
                label = "NGHIENG_GAP_DUOI" if tid%2 else "NONE"
                mode = "correct" if tid%2 else ("tilt_only", "bend_only", "wrong_direction", "early_release", "one_finger", "rest")[tid//2-1]
                save_trial(folder/"samples.csv", rows(mode, tid*6000, offset=s*15), "U01", sid, tid, label)

    def test_model_roundtrip_session_split_and_train_only_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            root, output = Path(d)/"data", Path(d)/"model"
            self.create_data(root)
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                result = train(["--data",str(root),"--output",str(output)])
            self.assertEqual(result, 0, out.getvalue())
            model = backend.SequenceModel(output)
            report = json.loads((output/"report.json").read_text())
            train_keys, test_keys = set(report["train_keys"]), set(report["test_keys"])
            self.assertEqual(report["evaluation_scope"], "session_holdout")
            self.assertFalse({k.split('/')[0] for k in train_keys}&{k.split('/')[0] for k in test_keys})
            for profile in model.guards.values():
                self.assertLessEqual(set(profile["training_keys"]), train_keys)
                self.assertFalse(set(profile["training_keys"])&test_keys)
            trials, _, _ = load_trials(root, backend)
            np.testing.assert_allclose(model.model[0].mean_, np.asarray([t["vector"] for t in trials if t["key"] in train_keys], dtype=float).mean(axis=0))
            self.assertEqual(model.predict(rows(), reference()), "NGHIENG_GAP_DUOI")
            for mode in ("tilt_only", "one_finger", "wrong_direction"):
                self.assertEqual(model.predict(rows(mode), reference()), "NONE")
            self.assertEqual(report["accuracy"], np.mean([p["actual"] == p["predicted"] for p in report["predictions"]]))

    def test_classifier_only_supports_single_finger_labels_and_persists_explicit_policy(self):
        with tempfile.TemporaryDirectory() as d:
            root, output = Path(d)/"data", Path(d)/"model"
            for sid in ("s1", "s2"):
                folder = root/sid
                folder.mkdir(parents=True)
                (folder/"imu_reference.json").write_text(json.dumps(reference(sid)))
                for tid in range(1,13):
                    label, mode = ("MY_SINGLE_FINGER", "one_finger") if tid%2 else ("NONE", "rest")
                    save_trial(folder/"samples.csv", rows(mode, tid*6000), "U01", sid, tid, label)
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                result = train(["--data",str(root),"--output",str(output),"--motion-checks","classifier-only"])
            self.assertEqual(result,0,out.getvalue())
            model = backend.SequenceModel(output)
            self.assertEqual(model.motion_checks,"classifier-only")
            self.assertEqual(model.guards,{})
            label,candidate,reason = model.predict_details(rows("one_finger"),reference())
            self.assertEqual(label,"MY_SINGLE_FINGER")
            self.assertEqual(label,candidate)
            self.assertIn("chua co kiem tra",reason)
            report = json.loads((output/"report.json").read_text())
            self.assertEqual(report["motion_checks"],"classifier-only")
            self.assertEqual(report["accuracy"],report["classifier_accuracy_before_motion_checks"])

    def test_single_session_requires_explicit_demo_override_and_old_duration_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/"data"
            self.create_data(root, sessions=1)
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                result = train(["--data",str(root),"--check-only"])
            self.assertEqual(result,1)
            self.assertIn("it nhat 2 phien", out.getvalue())
            ref = root/"s0"/"imu_reference.json"
            old = json.loads(ref.read_text()); old["trial_seconds"]=3
            ref.write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError,"incompatible reference/duration"):
                load_trials(root, backend)

    def test_collector_review_discards_wrong_attempt_and_mixes_labels(self):
        stream = Mock()
        stream.processor = SimpleNamespace(ready=True)
        stream.check_ready.return_value = {"hz":25}
        stream.capture.side_effect = [rows("rest")[:51], rows("rest")[:54],
                                      rows(start=10000), rows(start=16000), rows("tilt_only",start=22000)]
        answers = ["", "", "R", "", "", "", "", "Q"]
        with tempfile.TemporaryDirectory() as d:
            with patch.object(collect_sequence.socket,"create_connection"), \
                    patch.object(collect_sequence,"SampleStream",return_value=stream), \
                    patch.object(collect_sequence,"countdown"), \
                    patch("builtins.input",side_effect=answers), \
                    patch("sys.stdout",new_callable=io.StringIO):
                result = collect_sequence.main(["--user-id","U01","--output-dir",d], v2=True)
            self.assertEqual(result,0)
            paths = list(Path(d).glob("*/samples.csv"))
            self.assertEqual(len(paths),1)
            with paths[0].open(newline="") as f:
                saved = list(csv.DictReader(f))
            self.assertEqual(len(saved),252)
            self.assertEqual({r["label"] for r in saved[:126]}, {"NGHIENG_GAP_DUOI"})
            self.assertEqual({r["label"] for r in saved[126:]}, {"NONE"})
            self.assertEqual(float(saved[0]["timestamp"]),16000)
            self.assertEqual(float(saved[0]["flex_1"]),950)
            meta = json.loads(paths[0].with_name("imu_reference.json").read_text())
            self.assertEqual(meta["trial_seconds"],5)


if __name__ == "__main__":
    unittest.main()

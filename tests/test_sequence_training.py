"""Training integrity tests; generated values are not real accuracy evidence."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from SmartSignLanguage.collect_sequence import save_trial
from SmartSignLanguage.sensor_pipeline import ImuProcessor, make_imu_reference, Q_COLUMNS
from SmartSignLanguage.sequence_model import sequence_vector, SequenceModel, FEATURES, GRID
from SmartSignLanguage.train_sequence import load_trials, split_trials, main


def raw(flex=1000):
    return dict(flex_1=flex, flex_2=1100, ACCx=0, ACCy=0, ACCz=9.81, GYRx=0, GYRy=0, GYRz=0)


def reference(session="s1"):
    ref = make_imu_reference([{"timestamp": i*40, **raw()} for i in range(51)])
    ref.update(session_id=session, user_id="U01", trial_seconds=3)
    return ref


def rows(start=0, gesture=False):
    p = ImuProcessor(reference())
    return [p.process(start+i*40, raw(1000-(min(i, 75-i)*4 if gesture else 0))) for i in range(76)]


class SequenceTrainingTests(unittest.TestCase):
    def test_fixed_grid_keeps_order_and_ignores_quaternion_sign(self):
        batch = rows(gesture=True)
        x = sequence_vector(batch, reference())
        self.assertEqual(x.shape, (len(GRID)*len(FEATURES),))
        signed = [{**r, **{k: -r[k] for k in Q_COLUMNS}} if i%2 else r for i,r in enumerate(batch)]
        np.testing.assert_allclose(sequence_vector(signed, reference()), x)
        shifted = [dict(r, flex_1=r["flex_1"]+80, flex_2=r["flex_2"]-40) for r in batch]
        np.testing.assert_allclose(sequence_vector(shifted, reference()), x)
        reordered = [dict(r, flex_1=batch[(i+25)%len(batch)]["flex_1"]) for i,r in enumerate(batch)]
        self.assertFalse(np.allclose(sequence_vector(reordered, reference()), x))

    def test_short_or_gapped_trials_are_never_stretched(self):
        batch = rows()
        for invalid in (batch[:50], batch[:10]+batch[15:]):
            with self.assertRaises(ValueError):
                sequence_vector(invalid, reference())

    def test_splits_are_whole_trials_and_session_holdout_when_possible(self):
        trials = [{"session": f"s{s}", "label": label, "key": f"{s}/{label}/{i}"}
                  for s in range(3) for label in ("NONE", "MOVE") for i in range(4)]
        train, test, scope = split_trials(trials)
        self.assertEqual(scope, "session_holdout")
        self.assertFalse({trials[i]["session"] for i in train}&{trials[i]["session"] for i in test})
        pure = [dict(t, session=t["label"]) for t in trials]
        train, test, scope = split_trials(pure)
        self.assertEqual(scope, "within_session_trial_holdout")
        self.assertFalse(set(train)&set(test))
        for part in (train, test):
            self.assertEqual({pure[i]["label"] for i in part}, {"NONE", "MOVE"})

    def create_data(self, root):
        for sid, label in (("s1", "MOVE"), ("s2", "NONE")):
            folder = root/sid
            folder.mkdir()
            (folder/"imu_reference.json").write_text(json.dumps(reference(sid)))
            for tid in range(1, 7):
                save_trial(folder/"samples.csv", rows(tid*4000, label=="MOVE"), "U01", sid, tid, label)
        empty = root/"aborted"
        empty.mkdir()
        (empty/"samples.csv").write_text("timestamp,flex_1\n")

    def test_train_bundle_roundtrip_scaler_fit_only_on_training_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)/"data"
            root.mkdir()
            self.create_data(root)
            output = Path(d)/"model"
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["--data", str(root), "--output", str(output)]), 0)
            saved = SequenceModel(output)
            report = json.loads((output/"report.json").read_text())
            self.assertEqual(report["evaluation_scope"], "within_session_trial_holdout")
            self.assertTrue(report["warning"])
            self.assertEqual(saved.predict(rows(gesture=True), reference()), "MOVE")
            self.assertEqual(saved.predict(rows(), reference()), "NONE")
            trials, _, skipped = load_trials(root)
            self.assertEqual(len(skipped), 1)
            train = [t["vector"] for t in trials if t["key"] in report["train_keys"]]
            np.testing.assert_allclose(saved.model[0].mean_, np.asarray(train, dtype=float).mean(axis=0))
            original = (output/"model.joblib").read_bytes()
            with patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(main(["--data", str(root), "--output", str(output)]), 1)
            self.assertEqual((output/"model.joblib").read_bytes(), original)

    def test_loader_rejects_inconsistent_derived_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.create_data(root)
            path = root/"s1"/"samples.csv"
            with path.open(newline="") as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames
                batch = list(reader)
            batch[0]["ACCx_body"] = "100"
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(batch)
            with self.assertRaisesRegex(ValueError, "inconsistent derived"):
                load_trials(root)


if __name__ == "__main__":
    unittest.main()

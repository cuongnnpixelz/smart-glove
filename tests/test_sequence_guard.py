"""Sequence acceptance must require both fingers, direction, and temporal order."""
import unittest
import numpy as np

from SmartSignLanguage.sequence_guard import evaluate, flex_profile, check_open_pose


def profile():
    return {c: {"open_adc": 1000., "delta_adc": -100., "recovery_tolerance_adc": 10.}
            for c in ("flex_1", "flex_2")}


def sequence(mode="correct"):
    t = np.arange(0, 3001, 40)
    bend = np.interp(t, [0,240,480,2300,2700,3000], [0,0,1,1,0,0])
    tilt = np.interp(t, [0,700,1100,1600,2100,3000], [0,0,.8,.8,0,0])
    other = bend.copy()
    if mode == "tilt_only":
        bend[:]=0; other[:]=0
    if mode == "one_finger":
        other[:]=0
    if mode == "wrong_direction":
        tilt *= -1
    if mode == "tilt_before_bend":
        tilt = np.interp(t, [0,120,500,1000,1800,3000], [0,0,.8,.8,0,0])
    if mode == "release_before_return":
        bend = np.interp(t, [0,240,480,1300,1500,3000], [0,0,1,1,0,0]); other=bend.copy()
    if mode == "not_released":
        bend[t>2300]=1; other=bend.copy()
    if mode == "not_returned":
        tilt[t>1600]=.8
    return [{"timestamp":int(stamp), "flex_1":1000-100*b, "flex_2":1000-100*c,
             "Qw":float(np.cos(a/2)), "Qx":0., "Qy":float(np.sin(a/2)), "Qz":0.}
            for stamp,b,c,a in zip(t,bend,other,tilt)]


class SequenceGuardTests(unittest.TestCase):
    def test_correct_sequence_accepted_and_counterexamples_rejected(self):
        direction = {"axis":[0,1,0], "angle_rad":.8}
        self.assertTrue(evaluate(sequence(), profile(), direction)[0])
        for mode in ("tilt_only", "one_finger", "wrong_direction", "tilt_before_bend",
                     "release_before_return", "not_released", "not_returned"):
            with self.subTest(mode=mode):
                self.assertFalse(evaluate(sequence(mode), profile(), direction)[0])
        self.assertIn("flex_2", evaluate(sequence("one_finger"), profile(), direction)[1])

    def test_missing_data_and_stale_open_reference_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(sequence()[:25], profile(), {"axis":[0,1,0], "angle_rad":.8})
        with self.assertRaises(ValueError):
            check_open_pose([dict(r, flex_2=950) for r in sequence()], profile())

    def test_report_requires_both_channels_and_recovery(self):
        def pose(a=1000,b=1100):
            return [{"timestamp":i*40,"flex_1":a+(-1)**i,"flex_2":b+(-1)**i} for i in range(51)]
        poses = {"open_before":pose(),"index_bent":pose(1000,900),
                 "open_after_index":pose(),"middle_bent":pose(800,1100),"open_after_middle":pose()}
        self.assertEqual(set(flex_profile({"raw_poses":poses})), {"flex_1","flex_2"})
        poses["open_after_middle"] = pose(1000,1040)
        with self.assertRaisesRegex(ValueError,"flex_2"):
            flex_profile({"raw_poses":poses})


if __name__ == "__main__":
    unittest.main()

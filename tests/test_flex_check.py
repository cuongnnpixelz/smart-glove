"""Flex screening must reject noise, ambiguous wiring, and poor recovery."""
import unittest

from SmartSignLanguage.check_flex import analyze, POSES


def pose(f1=1000, f2=1100):
    return [{"timestamp": i*40, "flex_1": f1+(-1)**i, "flex_2": f2+(-1)**i} for i in range(51)]


def healthy():
    return {"open_before": pose(), "index_bent": pose(800,1100),
            "open_after_index": pose(), "middle_bent": pose(1000,900),
            "open_after_middle": pose()}


class FlexCheckTests(unittest.TestCase):
    def test_good_distinct_responses_and_inverted_polarity(self):
        poses = healthy()
        report = analyze(poses)
        self.assertTrue(report["two_fingers_distinguishable"])
        self.assertTrue(report["ready_for_two_finger_demo"])
        self.assertEqual(report["suggested_mapping"], {"Index":"flex_1", "Middle":"flex_2"})
        poses["index_bent"] = pose(1200,1100)
        self.assertTrue(analyze(poses)["two_fingers_distinguishable"])

    def test_noise_only_is_not_a_finger_response(self):
        report = analyze({name: pose() for name,_ in POSES})
        self.assertFalse(report["two_fingers_distinguishable"])
        self.assertFalse(report["responses"]["Index"]["flex_1"]["clear_response"])

    def test_slow_return_and_both_channels_moving_are_not_passed(self):
        poses = healthy()
        poses["open_after_index"] = pose(850,1100)
        poses["middle_bent"] = pose(850,900)
        poses["open_after_middle"] = pose(850,1100)
        report = analyze(poses)
        self.assertTrue(report["two_fingers_distinguishable"])
        self.assertFalse(report["ready_for_two_finger_demo"])
        self.assertFalse(report["finger_readiness"]["Index"]["returned_at_check"])
        poses = healthy()
        poses["index_bent"] = pose(800,900)
        self.assertFalse(analyze(poses)["two_fingers_distinguishable"])

    def test_drift_while_other_finger_moves_is_reported_separately(self):
        poses = healthy()
        poses["open_after_middle"] = pose(940,1100)
        report = analyze(poses)
        self.assertTrue(report["two_fingers_distinguishable"])
        self.assertTrue(report["finger_readiness"]["Index"]["returned_at_check"])
        self.assertFalse(report["finger_readiness"]["Index"]["stable_when_other_finger_moves"])
        self.assertFalse(report["ready_for_two_finger_demo"])

    def test_broken_timing_cannot_be_reported_as_sensor_failure(self):
        poses = healthy()
        poses["index_bent"][20]["timestamp"] += 1000
        with self.assertRaises(ValueError):
            analyze(poses)

    def test_real_bend_with_slow_drift_is_not_reported_as_no_response(self):
        poses = healthy()
        for i, row in enumerate(poses["index_bent"]):
            row["flex_1"] = 920-i*.8
        poses["open_after_index"] = pose(970,1100)
        poses["middle_bent"] = pose(970,900)
        poses["open_after_middle"] = pose(970,1100)
        report = analyze(poses)
        response = report["responses"]["Index"]["flex_1"]
        self.assertTrue(response["clear_response"])
        self.assertFalse(response["stable_during_poses"])
        self.assertFalse(response["returned_at_check"])
        self.assertLessEqual(response["recovery_tolerance_adc"], .25*abs(response["delta_adc"]))
        self.assertTrue(report["two_fingers_distinguishable"])
        self.assertFalse(report["ready_for_two_finger_demo"])


if __name__ == "__main__":
    unittest.main()

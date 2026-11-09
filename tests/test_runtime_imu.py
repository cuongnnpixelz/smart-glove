"""Written recovery regression cases; run separately when execution is authorized."""
import unittest
import numpy as np

from SmartSignLanguage.sensor_pipeline import ImuProcessor, make_imu_reference, SamplingGap
from SmartSignLanguage.runtime_imu import RuntimeImuProcessor
from SmartSignLanguage.continuous_sequence import ContinuousSegmenter


def raw(**changes):
    return dict(dict(flex_1=950,flex_2=1050,ACCx=0,ACCy=0,ACCz=9.81,
                     GYRx=0,GYRy=0,GYRz=0),**changes)


def warmed():
    reference = make_imu_reference([dict(raw(),timestamp=t) for t in range(0,2040,40)])
    processor = ImuProcessor(reference)
    for t in range(0,2040,40): processor.process(t,raw())
    return processor


class RuntimeImuTests(unittest.TestCase):
    def test_short_gap_discards_orientation_and_seeds_only_new_stable_samples(self):
        processor = RuntimeImuProcessor(warmed())
        first = processor.process(2230,raw())
        self.assertEqual(first["_runtime_gap_ms"],230)
        self.assertTrue(first["_runtime_recovering"])
        self.assertNotIn("Qw",first)
        for t in range(2270,3030,40):
            self.assertTrue(processor.process(t,raw())["_runtime_recovering"])
        recovered = processor.process(3030,raw())
        seed = recovered["_runtime_seed"]
        self.assertEqual(seed[0]["timestamp"],2230)
        self.assertEqual(seed[-1]["timestamp"]-seed[0]["timestamp"],800)
        self.assertTrue(all("_runtime_recovering" not in r for r in seed))
        np.testing.assert_allclose([recovered[k] for k in ("ACCx_body","ACCy_body","ACCz_body")],0,atol=1e-5)
        detector = ContinuousSegmenter(processor.calibration,lambda *_: self.fail("No prediction during recovery"))
        events = [e for row in seed if (e:=detector.push(row))]
        self.assertEqual(events[-1],{"state":"READY"})
        self.assertNotIn("_runtime_seed",processor.process(3070,raw()))

    def test_motion_delays_recovery_and_repeated_gap_restarts_stability_timer(self):
        processor = RuntimeImuProcessor(warmed())
        processor.process(2230,raw())
        for t in range(2270,3271,40):
            self.assertTrue(processor.process(t,raw(GYRy=.5))["_runtime_recovering"])
        again = processor.process(3500,raw())
        self.assertEqual(again["_runtime_gap_ms"],230)
        for t in range(3540,4300,40):
            self.assertTrue(processor.process(t,raw())["_runtime_recovering"])
        self.assertEqual(processor.process(4300,raw())["_runtime_seed"][0]["timestamp"],3500)

    def test_long_gap_reset_and_bad_data_remain_fatal(self):
        with self.assertRaises(SamplingGap): RuntimeImuProcessor(warmed()).process(2501,raw())
        with self.assertRaises(ValueError): RuntimeImuProcessor(warmed()).process(0,raw())
        with self.assertRaises(ValueError): RuntimeImuProcessor(warmed()).process(2040,raw(ACCx=float("nan")))

    def test_collection_processor_still_rejects_230ms(self):
        with self.assertRaises(SamplingGap): warmed().process(2230,raw())


if __name__ == "__main__": unittest.main()

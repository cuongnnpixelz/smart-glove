"""Real sample counts and calibration invariants for configurable phrases."""
from copy import deepcopy
import unittest

from SmartSignLanguage import phrase_data
from SmartSignLanguage.five_finger import (
    CALIBRATION_SCHEMA, CSV_COLUMNS, FLEX_COLUMNS, FLEX_PINS, FINGERS,
    validate_reference as validate_word_reference,
)
from SmartSignLanguage.sensor_pipeline import make_imu_reference


def samples(count=300, start=0):
    return [dict(timestamp=start+i*10, **{key: 1000 for key in FLEX_COLUMNS},
                 ACCx=0, ACCy=0, ACCz=9.81, GYRx=0, GYRy=0, GYRz=0)
            for i in range(count)]


def calibration():
    reference = make_imu_reference(samples(201), sample_ms=10)
    entry = dict(open=1000, closed=800, noise_p90=0,
                 open_p05=1000, open_p95=1000, open_drift=0,
                 closed_p05=800, closed_p95=800, closed_drift=0)
    reference.update(
        trial_seconds=1.5, sample_count=150, csv_columns=list(CSV_COLUMNS),
        flex_pins=FLEX_PINS, fingers=FINGERS,
        flex_calibration_schema=CALIBRATION_SCHEMA,
        flex_calibration={key: dict(entry) for key in FLEX_COLUMNS},
        divider_ohms=10000, supply_volts=3.3, divider_topology="3V3-flex-ADC-10k-GND",
        collection_protocol="five-flex-calibrated-100hz-1.5s-v2",
    )
    return reference


class PhraseDataTests(unittest.TestCase):
    def test_expanded_range_requires_metadata_and_still_rejects_saturation(self):
        batch = samples(300)
        batch[200]['GYRx'] = 6.0
        batch[200]['ACCx'] = 25.0
        with self.assertRaisesRegex(ValueError, 'MPU'):
            phrase_data.phrase_quality(batch, 3)
        ref = {'imu_ranges': {'accel_g': 4, 'gyro_deg_s': 500, 'dlpf_hz': 21}}
        phrase_data.phrase_quality(batch, 3, ref)
        batch[250]['GYRy'] = 8.7
        with self.assertRaisesRegex(ValueError, 'GYRy'):
            phrase_data.phrase_quality(batch, 3, ref)

    def test_duration_requires_real_sample_boundaries_and_finite_limits(self):
        for value, expected in [("3", 300), (5, 500), (3.25, 325), (1, 100), (10, 1000)]:
            with self.subTest(value=value):
                self.assertEqual(phrase_data.sample_count(value), expected)
        for value in [True, None, "bad", 0, .5, 10.01, float("nan"), float("inf"), 3.005]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                phrase_data.validate_duration(value)

    def test_three_five_and_ten_seconds_keep_all_samples(self):
        for seconds in (3, 5, 10):
            batch = samples(seconds*100, start=45000)
            quality = phrase_data.phrase_quality(batch, seconds)
            self.assertEqual(quality["samples"], seconds*100)
            self.assertEqual(quality["hz"], 100)
            self.assertEqual(quality["duration_ms"], seconds*1000-10)
        with self.assertRaisesRegex(ValueError, "300 mau that"):
            phrase_data.phrase_quality(samples(150), 3)

    def test_missing_extra_duplicate_and_slow_samples_are_not_repaired(self):
        valid = samples(300)
        missing = valid[:155]+valid[156:]
        extra = samples(301)
        duplicate = deepcopy(valid)
        duplicate[230]["timestamp"] = duplicate[229]["timestamp"]
        slow = [dict(row, timestamp=index*11) for index, row in enumerate(valid)]
        gap = [dict(row, timestamp=row["timestamp"]+(30 if index >= 230 else 0))
               for index, row in enumerate(valid)]
        for name, batch in [("missing", missing), ("extra", extra), ("duplicate", duplicate),
                            ("slow", slow), ("gap", gap)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                phrase_data.phrase_quality(batch, 3)

    def test_late_corruption_and_saturation_are_checked_beyond_old_150_samples(self):
        for column, value, error in [("flex_4", 4095, "GPIO 35"), ("flex_1", 0, "GPIO 32"),
                                     ("GYRx", 4.34, "MPU"), ("ACCz", -19.5, "MPU"),
                                     ("flex_2", float("nan"), "khong huu han")]:
            batch = samples(500)
            batch[450][column] = value
            with self.subTest(column=column, value=value), self.assertRaisesRegex(ValueError, error):
                phrase_data.phrase_quality(batch, 5)

    def test_reference_preserves_calibration_and_is_rejected_by_old_model_format(self):
        source = calibration()
        snapshot = deepcopy(source)
        phrase = phrase_data.make_phrase_reference(source)
        self.assertEqual(source, snapshot)
        self.assertEqual(phrase["csv_columns"], list(CSV_COLUMNS))
        self.assertEqual(phrase["flex_calibration"], source["flex_calibration"])
        phrase_data.validate_phrase_reference(phrase)
        with self.assertRaises(ValueError):
            validate_word_reference(phrase)
        phrase["flex_calibration"]["flex_1"]["open"] = 4095
        self.assertEqual(source, snapshot)
        with self.assertRaises(ValueError):
            phrase_data.validate_phrase_reference(phrase)

    def test_per_label_metadata_records_actual_duration(self):
        reference = phrase_data.make_phrase_reference(calibration())
        reference["label_settings"] = {
            "TOI_CAM_ON_BAN": {"seconds": 3, "sample_count": 300, "display_text": "Toi cam on ban"},
            "CAU_DAI": {"seconds": 5, "sample_count": 500, "display_text": "Cau dai"},
        }
        phrase_data.validate_phrase_reference(reference)
        reference["label_settings"]["CAU_DAI"]["sample_count"] = 300
        with self.assertRaisesRegex(ValueError, "CAU_DAI"):
            phrase_data.validate_phrase_reference(reference)


if __name__ == "__main__":
    unittest.main()

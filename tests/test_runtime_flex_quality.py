import copy
import unittest
from unittest.mock import Mock, patch

import numpy as np

from SmartSignLanguage.collect_sequence_5 import collection_quality
from SmartSignLanguage.runtime_flex_quality import recognition_quality
from SmartSignLanguage.sequence_model_5 import sequence_vector
from SmartSignLanguage.none_sentence_capture import NoneSentenceDecoder
from test_five_finger import rows, reference


class RuntimeFlexQualityTests(unittest.TestCase):
    def test_brief_spikes_use_existing_model_filter_without_mutating_raw_data(self):
        for indices in ([58], [58, 59]):
            with self.subTest(indices=indices):
                clean, ref = rows(), reference()
                batch = copy.deepcopy(clean)
                for i in indices:
                    batch[i]['flex_4'] += 476
                original = copy.deepcopy(batch)
                with self.assertRaisesRegex(ValueError, 'F4'):
                    collection_quality(batch, ref)
                quality = recognition_quality(batch, ref)
                self.assertEqual(len(quality['flex_spike_samples']), len(indices))
                self.assertEqual(batch, original)
                np.testing.assert_array_equal(sequence_vector(batch, ref), sequence_vector(clean, ref))

    def test_in_range_jumps_do_not_interrupt_recognition(self):
        for indices in (range(58, 150), range(58, 61), [20, 60, 100], [0], [149]):
            with self.subTest(indices=indices):
                batch = rows()
                for i in indices:
                    batch[i]['flex_4'] += 476
                recognition_quality(batch, reference())
                with self.assertRaisesRegex(ValueError, 'F4'):
                    collection_quality(batch, reference())

    def test_rails_gaps_and_imu_clipping_are_not_filtered(self):
        for key, value in (('flex_4', 0), ('flex_4', 4095), ('flex_4', float('nan')),
                           ('timestamp', 9999), ('GYRx', 20)):
            with self.subTest(key=key, value=value):
                batch = rows()
                batch[58][key] = value
                with self.assertRaises(ValueError):
                    recognition_quality(batch, reference())

    def test_smooth_motion_and_small_endpoint_overshoot_are_allowed(self):
        batch, ref = rows(), reference()
        for i, row in enumerate(batch):
            row['flex_4'] += 40 * np.sin(i / 10)
        recognition_quality(batch, ref)

    def test_large_persistent_offset_is_not_recalibrated_away(self):
        batch, ref = rows(), reference()
        ref['flex_calibration']['flex_4'].update(open=900, closed=850)
        for row in batch:
            row['flex_4'] = 2100
        original = copy.deepcopy(ref)
        recognition_quality(batch, ref)
        self.assertEqual(ref, original)
        with self.assertRaisesRegex(ValueError, 'F4'):
            collection_quality(batch, ref)

    def test_none_decoder_continues_after_brief_spike_with_raw_samples_intact(self):
        batch = rows()
        batch[58]['flex_4'] += 476
        model = Mock()
        model.predict.return_value = 'NONE'
        decoder = NoneSentenceDecoder(model, reference(), none_windows=1)
        with patch('builtins.print'):
            for row in batch:
                decoder.push(row)
        self.assertTrue(decoder.done)
        self.assertEqual(decoder.votes, ['NONE'])
        self.assertEqual(model.predict.call_args.args[0][58]['flex_4'], 1776)


if __name__ == '__main__':
    unittest.main()

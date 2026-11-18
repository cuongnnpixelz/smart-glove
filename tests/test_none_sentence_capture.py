import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage.none_sentence_capture import NoneSentenceDecoder
from SmartSignLanguage.predict_sentence_words import filter_window_predictions


class NoneEndTests(unittest.TestCase):
    def decode(self, labels):
        model = Mock()
        model.predict.side_effect = labels
        decoder = NoneSentenceDecoder(model, {})
        with patch('SmartSignLanguage.none_sentence_capture.recognition_quality'), patch('builtins.print'):
            for i in range(150 + 25 * (len(labels) - 1)):
                decoder.push({'timestamp': i * 10})
        return decoder

    def test_long_sentence_and_ten_none(self):
        labels = ['TOI'] * 10 + ['CAM_ON'] * 3 + ['BAN'] * 10 + ['NONE'] * 10
        d = self.decode(labels)
        self.assertTrue(d.done)
        self.assertGreater(len(d.rows), 500)
        self.assertEqual(filter_window_predictions(d.votes)[0], ['TOI', 'CAM_ON', 'BAN'])

    def test_interrupted_none_resets(self):
        d = self.decode(['NONE'] * 9 + ['GI'] + ['NONE'] * 9)
        self.assertFalse(d.done)
        self.assertEqual(d.none_count, 9)

    def test_sensor_failure_is_not_none(self):
        d = NoneSentenceDecoder(Mock(), {})
        with patch('SmartSignLanguage.none_sentence_capture.recognition_quality', side_effect=ValueError('F4')):
            with self.assertRaisesRegex(ValueError, 'F4'):
                for i in range(150):
                    d.push({'timestamp': i * 10})
        self.assertEqual(d.votes, [])

    def test_intermittent_flex_fault_skips_windows_and_recovers_without_joining_words(self):
        model = Mock()
        model.predict.side_effect = ['TOI', 'BAN']
        d = NoneSentenceDecoder(model, {})
        with patch('SmartSignLanguage.none_sentence_capture.recognition_quality',
                   side_effect=[{}, ValueError('NGHI LOI FLEX F4'),
                                ValueError('NGHI LOI FLEX F4'), {}, {}]), patch('builtins.print') as output:
            for i in range(250):
                d.push({'timestamp': i * 10})
        self.assertEqual(d.votes, ['BAN'])
        self.assertEqual(model.predict.call_count, 2)
        self.assertFalse(d.waiting_clean_flex)
        self.assertFalse(d.done)
        self.assertEqual(output.call_count, 2)


if __name__ == '__main__':
    unittest.main()

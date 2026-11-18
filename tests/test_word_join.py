import unittest
from unittest.mock import Mock, patch
from SmartSignLanguage.predict_continuous_5 import WordJoinRecognizer


class WordJoinTests(unittest.TestCase):
    def setUp(self):
        self.model = Mock(manifest={'labels': ['NONE', 'TOI', 'BAN']})
        self.recognizer = WordJoinRecognizer(self.model, {})
        self.stamp = 0
        self.quality = patch('SmartSignLanguage.predict_continuous_5.trial_quality',
                             return_value={'hz': 100})
        self.quality.start()
        self.addCleanup(self.quality.stop)

    def feed(self, label, batches=1):
        self.model.predict.return_value = label
        events = []
        for _ in range(batches):
            rows = [{'timestamp': self.stamp + i * 10} for i in range(25)]
            self.stamp += 250
            event = self.recognizer.update(rows)
            if event:
                events.append(event)
        return events

    def test_words_require_none_and_emit_once_including_repeated_word(self):
        self.assertEqual(self.feed('TOI', 15), [])
        self.feed('NONE', 8)
        self.assertTrue(self.recognizer.armed)
        events = self.feed('TOI', 12)
        self.assertEqual([e['label'] for e in events if e['state'] == 'RESULT'], ['TOI'])
        self.feed('BAN', 12)
        self.assertEqual(self.recognizer.words, ['TOI'])
        self.feed('NONE', 8)
        self.feed('TOI', 12)
        self.assertEqual(self.recognizer.words, ['TOI', 'TOI'])

    def test_unstable_labels_are_not_joined(self):
        self.feed('NONE', 8)
        for _ in range(12):
            self.feed('TOI')
            self.feed('BAN')
        self.assertEqual(self.recognizer.words, [])

    def test_gap_revokes_arming_and_keeps_accepted_words(self):
        self.feed('NONE', 8)
        self.feed('TOI', 12)
        self.feed('NONE', 8)
        self.stamp += 100
        self.feed('BAN', 15)
        self.assertFalse(self.recognizer.armed)
        self.assertEqual(self.recognizer.words, ['TOI'])

    def test_sensor_error_requires_rest_again(self):
        self.feed('NONE', 8)
        self.feed('TOI', 5)
        with patch('SmartSignLanguage.predict_continuous_5.trial_quality', side_effect=ValueError('bad sensor')):
            events = self.feed('TOI')
        self.assertEqual(events[0]['state'], 'ERROR')
        self.feed('TOI', 15)
        self.assertEqual(self.recognizer.words, [])

    def test_missing_none_is_rejected(self):
        with self.assertRaises(ValueError):
            WordJoinRecognizer(Mock(manifest={'labels': ['TOI']}), {})


if __name__ == '__main__':
    unittest.main()

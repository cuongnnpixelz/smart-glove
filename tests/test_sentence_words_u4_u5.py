import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage.predict_sentence_words import (
    DEFAULT_MODEL, WORD_TEXT, filter_window_predictions, format_sentence,
    decode_five_seconds,
)
from SmartSignLanguage.sequence_model_5 import SequenceModel


class SentenceWordsTests(unittest.TestCase):
    def test_wave_split_by_background(self):
        votes = ['NONE'] * 2 + ['CHAO'] * 2 + ['NONE'] * 4 + ['CHAO'] * 2 + ['NONE'] * 6
        words, _ = filter_window_predictions(votes)
        self.assertEqual(format_sentence(words), 'XIN CHÀO')

    def test_wave_exception_does_not_join_singletons_or_cross_other_words(self):
        self.assertEqual(filter_window_predictions(['CHAO', 'NONE'] * 4)[0], [])
        self.assertEqual(filter_window_predictions(['CHAO'] * 2 + ['NONE'] * 3)[0], [])
        self.assertEqual(filter_window_predictions(['CHAO'] * 2 + ['TOI'] + ['CHAO'] * 2)[0], [])

    def test_user_example_and_transition_noise(self):
        votes = ['TOI'] * 3 + ['CHAO'] * 2 + ['CAM_ON'] * 3 + ['BAN'] * 3
        words, _ = filter_window_predictions(votes)
        self.assertEqual(words, ['TOI', 'CAM_ON', 'BAN'])
        self.assertEqual(format_sentence(words), 'TÔI CẢM ƠN BẠN')

    def test_none_does_not_join_weak_evidence(self):
        words, _ = filter_window_predictions(['TOI'] * 2 + ['NONE'] + ['TOI'] * 2)
        self.assertEqual(words, [])

    def test_new_vocabulary_order_and_duplicates(self):
        words, _ = filter_window_predictions(['BAN'] * 3 + ['TEN'] * 4 + ['GI'] * 3)
        self.assertEqual(format_sentence(words), 'BẠN TÊN GÌ')
        words, _ = filter_window_predictions(['TOI'] * 3 + ['CHAO'] + ['TOI'] * 3)
        self.assertEqual(words, ['TOI'])

    def test_old_stricter_threshold_is_available(self):
        self.assertEqual(filter_window_predictions(['TOI'] * 3, 4)[0], [])
        self.assertEqual(filter_window_predictions(['CAM_ON'], 4)[0], [])
        self.assertEqual(filter_window_predictions(['CAM_ON'] * 3, 4)[0], ['CAM_ON'])

    def test_requested_word_thresholds_require_consecutive_windows(self):
        for word, minimum in [('DI_DAU', 4), ('O_DAU', 4), ('TUYET_VOI', 4),
                              ('CAM_ON', 3), ('TEN', 3)]:
            with self.subTest(word=word):
                self.assertEqual(filter_window_predictions([word] * (minimum - 1), 5)[0], [])
                self.assertEqual(filter_window_predictions([word] * minimum, 5)[0], [word])
                self.assertEqual(filter_window_predictions(
                    [word] * (minimum - 1) + ['NONE'] + [word], 5)[0], [])

    def test_sensor_error_cannot_silently_bridge_windows(self):
        rows = [{'timestamp': i * 10} for i in range(200)]
        model = Mock()
        model.predict.return_value = 'TOI'
        with patch('SmartSignLanguage.predict_sentence_words.recognition_quality',
                   side_effect=[{}, ValueError('F3 GPIO34')]):
            with self.assertRaisesRegex(ValueError, 'GPIO34'):
                decode_five_seconds(rows, model, {})

    def test_saved_combined_model_has_all_display_labels(self):
        model = SequenceModel(DEFAULT_MODEL)
        labels = set(model.manifest['labels']) - {'NONE'}
        self.assertEqual(len(labels), 11)
        self.assertTrue(labels <= WORD_TEXT.keys())


if __name__ == '__main__':
    unittest.main()

import unittest
from SmartSignLanguage.predict_sentence_words import filter_window_predictions


class NameContextTests(unittest.TestCase):
    def test_reported_sentence_preserves_raw_evidence(self):
        runs = [['BAN', 3], ['TOI', 5], ['TEN', 3], ['TOI', 3],
                ['BUON_BA', 2], ['KHOE', 1], ['GI', 7], ['NONE', 10]]
        votes = [word for word, count in runs for _ in range(count)]
        words, raw = filter_window_predictions(votes)
        self.assertEqual(words, ['BAN', 'TEN', 'GI'])
        self.assertEqual(raw, runs)

    def test_no_name_evidence_no_replacement(self):
        self.assertEqual(filter_window_predictions(['BAN']*3 + ['TOI']*5 + ['GI']*3)[0],
                         ['BAN', 'TOI', 'GI'])

    def test_context_cannot_promote_one_or_two_name_windows(self):
        for count in (1, 2):
            votes = ['BAN'] * 5 + ['TOI'] * 5 + ['TEN'] * count + ['GI'] * 5
            self.assertEqual(filter_window_predictions(votes, 5)[0], ['BAN', 'TOI', 'GI'])

    def test_first_person_name_unchanged(self):
        self.assertEqual(filter_window_predictions(['TOI']*5 + ['TEN']*3)[0], ['TOI', 'TEN'])

    def test_stable_other_word_not_discarded(self):
        votes = ['BAN']*3 + ['TOI']*5 + ['TEN'] + ['KHOE']*3 + ['GI']*3
        self.assertEqual(filter_window_predictions(votes)[0], ['BAN', 'TOI', 'KHOE', 'GI'])

    def test_none_boundary_not_bridged(self):
        votes = ['BAN']*3 + ['TOI']*5 + ['NONE']*10 + ['TEN'] + ['GI']*3
        self.assertEqual(filter_window_predictions(votes)[0], ['BAN', 'TOI', 'GI'])

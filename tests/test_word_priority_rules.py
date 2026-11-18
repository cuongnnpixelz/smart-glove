import unittest
from SmartSignLanguage.predict_sentence_words import filter_window_predictions


class PriorityRulesTests(unittest.TestCase):
    def test_exact_eat_wonderful_confusion(self):
        self.check([('AN', 5), ('TUYET_VOI', 3), ('O_DAU', 1), ('BUON_BA', 3)], ['TUYET_VOI'])
        self.check([('TOI', 5), ('AN', 5), ('TUYET_VOI', 3), ('O_DAU', 1),
                    ('BUON_BA', 3), ('CAM_ON', 3)], ['TOI', 'TUYET_VOI', 'CAM_ON'])

    def test_short_wonderful_alone_stays_below_threshold(self):
        self.check([('TUYET_VOI', 3)], [])
        self.check([('AN', 5)], ['AN'])

    def check(self, runs, expected):
        votes = [word for word, count in runs for _ in range(count)]
        words, raw = filter_window_predictions(votes, 5)
        self.assertEqual(words, expected)
        self.assertEqual(raw, [list(r) for r in runs])

    def test_requested_health_example(self):
        self.check([('DI_DAU', 4), ('KHOE', 2), ('CHAO', 5)], ['KHOE'])

    def test_surrounding_words_remain(self):
        self.check([('TOI', 5), ('DI_DAU', 4), ('KHOE', 2), ('CHAO', 5),
                    ('CAM_ON', 3)], ['TOI', 'KHOE', 'CAM_ON'])

    def test_wonderful_priority(self):
        self.check([('TUYET_VOI', 4), ('BUON_BA', 9)], ['TUYET_VOI'])

    def test_weak_intervening_word_does_not_block_priority(self):
        self.check([('TUYET_VOI', 4), ('O_DAU', 1), ('BUON_BA', 9)], ['TUYET_VOI'])

    def test_where_priority_requires_supported_where(self):
        self.check([('DI_DAU', 4), ('O_DAU', 4)], ['O_DAU'])
        self.check([('DI_DAU', 4), ('O_DAU', 1)], ['DI_DAU'])
        self.check([('DI_DAU', 4), ('NONE', 1), ('O_DAU', 4)], ['DI_DAU', 'O_DAU'])

    def test_supported_intervening_word_remains(self):
        self.check([('TUYET_VOI', 4), ('O_DAU', 4), ('BUON_BA', 9)],
                   ['TUYET_VOI', 'O_DAU', 'BUON_BA'])

    def test_none_boundary_and_unrelated_words_are_not_bridged(self):
        self.check([('TUYET_VOI', 4), ('NONE', 2), ('BUON_BA', 5)], ['TUYET_VOI', 'BUON_BA'])
        self.check([('DI_DAU', 4), ('NONE', 1), ('KHOE', 2), ('CHAO', 5)], ['DI_DAU', 'CHAO'])

    def test_individual_labels_remain(self):
        for word in ('DI_DAU', 'KHOE', 'CHAO', 'TUYET_VOI', 'BUON_BA'):
            self.check([(word, 5)], [word])

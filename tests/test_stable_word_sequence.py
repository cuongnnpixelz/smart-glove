import unittest
from SmartSignLanguage.word_sequence_join import StableWordSequence


class StableSequenceTests(unittest.TestCase):
    def setUp(self):
        self.joiner=StableWordSequence(['BAN','TOI','KHOE','CAM_ON','CHAO','NONE','TU_MOI'])
        self.stamp=0

    def feed(self,label,count):
        events=[]
        for _ in range(count):
            event=self.joiner.update(label,self.stamp)
            self.stamp+=250
            if event:events.append(event)
        return events

    def test_user_transition_pattern_does_not_insert_short_toi(self):
        # Reconstructed prediction pattern, not raw sensor replay or an
        # accuracy claim. Includes first candidates hidden by old confirmations.
        self.feed('BAN',8)
        self.feed('TOI',3)
        self.feed('KHOE',2)
        self.feed('TOI',2)
        self.feed('KHOE',7)
        self.assertEqual(self.joiner.words,['BAN','KHOE'])

    def test_intentional_stable_toi_is_not_blacklisted(self):
        self.feed('BAN',5);self.feed('TOI',5);self.feed('KHOE',5)
        self.assertEqual(self.joiner.words,['BAN','TOI','KHOE'])

    def test_hold_and_brief_noise_do_not_repeat_committed_word(self):
        self.feed('BAN',20);self.feed('TOI',2);self.feed('BAN',10)
        self.assertEqual(self.joiner.words,['BAN'])

    def test_none_finalizes_once_and_allows_same_word_next_turn(self):
        self.feed('BAN',5)
        events=self.feed('NONE',15)
        final=[e for e in events if e['state']=='FINAL']
        self.assertEqual(final,[{'state':'FINAL','words':['BAN']}])
        self.feed('BAN',5)
        self.assertEqual(self.joiner.words,['BAN'])

    def test_vocabulary_is_not_hardcoded_to_five_words(self):
        self.feed('TU_MOI',5)
        self.assertEqual(self.joiner.words,['TU_MOI'])

    def test_gap_discards_pending_and_old_chain(self):
        self.feed('BAN',5);self.feed('TOI',3)
        with self.assertRaises(ValueError):self.joiner.update('TOI',self.stamp+1000)
        self.assertEqual(self.joiner.words,[])
        self.assertIsNone(self.joiner.candidate)

    def test_no_word_on_alternating_predictions_or_short_none(self):
        for _ in range(8):self.feed('BAN',2);self.feed('TOI',2)
        self.assertEqual(self.joiner.words,[])
        self.feed('KHOE',5);self.feed('NONE',2);self.feed('KHOE',5)
        self.assertEqual(self.joiner.words,['KHOE'])

    def test_stable_wrong_label_is_not_claimed_to_be_rejected(self):
        self.feed('TOI',5)
        self.assertEqual(self.joiner.words,['TOI'])


if __name__=='__main__':unittest.main()

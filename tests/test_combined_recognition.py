import unittest
from unittest.mock import Mock
from SmartSignLanguage.combined_recognition import CombinedModel


class CombinedTests(unittest.TestCase):
    def run_episode(self, phrases, words):
        model=CombinedModel.__new__(CombinedModel)
        model.phrase=Mock(durations=[3.0,5.0])
        model.phrase.predict.side_effect=phrases
        model.word=Mock()
        model.word.predict.side_effect=words
        result=model.predict_episode([{'timestamp':i*10} for i in range(501)],{})
        self.assertTrue(all(len(c.args[0])==150 for c in model.word.predict.call_args_list))
        return result

    def test_conflict_abstains(self):
        self.assertEqual(self.run_episode(['CAU','NONE'],['TU','TU','NONE'])['state'],'WAIT')

    def test_word_requires_repeated_support(self):
        self.assertEqual(self.run_episode(['NONE','NONE'],['TU','NONE','NONE'])['state'],'NONE')
        self.assertEqual(self.run_episode(['NONE','NONE'],['TU','TU','NONE'])['label'],'TU')

    def test_phrase_and_background(self):
        self.assertEqual(self.run_episode(['CAU','NONE'],['NONE']*3)['label'],'CAU')
        self.assertEqual(self.run_episode(['NONE']*2,['NONE']*3)['state'],'NONE')

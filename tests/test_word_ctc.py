import unittest
import torch
from SmartSignLanguage.train_word_ctc import Network, decode, errors, VAL, TEST


class WordCTCTests(unittest.TestCase):
    def test_repeated_words_need_blank_separation(self):
        self.assertEqual(decode([0,1,1,0,1,2,2,0]), ['TOI','TOI','CAM_ON'])
        self.assertEqual(decode([0,0]), [])

    def test_edit_counts_include_background_hallucinations(self):
        self.assertEqual(errors([], ['BAN']), (0,0,1))
        self.assertEqual(errors(['BAN'], []), (0,1,0))
        self.assertEqual(errors(['TOI','BAN'], ['TOI','KHOE']), (1,0,0))

    def test_causal_network(self):
        torch.manual_seed(1)
        model = Network().eval()
        a = torch.randn(1,30,19)
        b = a.clone(); b[:,15:] = 100
        with torch.no_grad():
            self.assertTrue(torch.allclose(model(a)[:,:15],model(b)[:,:15]))

    def test_selection_and_test_sessions_disjoint(self):
        self.assertFalse(VAL & TEST)


if __name__ == '__main__':
    unittest.main()

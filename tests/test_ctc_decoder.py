import collections
import itertools
import unittest
import numpy as np
from SmartSignLanguage.ctc_decode import prefix_beam, alignment_peaks


class DecoderTests(unittest.TestCase):
    def test_matches_sum_of_all_alignments(self):
        p=np.array([[.4,.35,.25],[.2,.5,.3],[.3,.2,.5]])
        totals=collections.defaultdict(float)
        for path in itertools.product(range(3),repeat=3):
            out=[];previous=None
            for value in path:
                if value and value!=previous:out.append(value)
                previous=value
            totals[tuple(out)]+=np.prod([p[i,label] for i,label in enumerate(path)])
        beam=prefix_beam(np.log(p),width=100)
        for seq,score in beam:
            self.assertAlmostEqual(np.exp(score),totals[seq])
        self.assertEqual(beam[0][0],max(totals,key=totals.get))

    def test_blank_and_repeated_token(self):
        p=np.array([[.01,.99],[.99,.01],[.01,.99]])
        self.assertEqual(prefix_beam(np.log(p))[0][0],(1,1))
        np.testing.assert_allclose(alignment_peaks(np.log(p),(1,1)),[.99,.99])
        self.assertEqual(alignment_peaks(np.log(p),()),[])
        self.assertEqual(alignment_peaks(np.log(p[:1]),(1,1)),[0,0])


if __name__=='__main__':unittest.main()

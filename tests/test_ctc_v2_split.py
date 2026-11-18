import unittest
from SmartSignLanguage.train_word_ctc_v2 import split
from SmartSignLanguage.train_word_ctc import VAL,TEST


class SplitTests(unittest.TestCase):
    def test_validation_does_not_consume_test_or_duplicate_training_trials(self):
        rows=[]
        for session in ['train_session',*VAL,*TEST]:
            for i in range(20):
                rows.append({'session':session,'key':session+'/'+str(i+1),
                             'kind':'continuous','label':'TOI_KHOE'})
        train,val,test=split(rows)
        groups=[{r['key'] for r in g} for g in (train,val,test)]
        self.assertFalse(groups[0]&groups[1] or groups[0]&groups[2] or groups[1]&groups[2])
        self.assertEqual(set.union(*groups),{r['key'] for r in rows})
        self.assertEqual({r['session'] for r in test},TEST)
        self.assertEqual(len(train),16)


if __name__=='__main__':unittest.main()

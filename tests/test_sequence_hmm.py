import unittest
import numpy as np
from SmartSignLanguage.sequence_hmm import WordHMM,OnlineWordHMM
from SmartSignLanguage.predict_join_hmm import SensorFrames
from SmartSignLanguage.train_word_ctc import features
from SmartSignLanguage.sequence_model_5 import FLEX_COLUMNS,legacy


class HMMTests(unittest.TestCase):
    def model(self):
        m=WordHMM(['A','B'],states=2)
        m.center=np.zeros(14);m.scale=np.ones(14)
        m.means=np.array([[0]*14,[1]*14,[2]*14,[3]*14,[4]*14],dtype=float)
        m.variances=np.ones((5,14))*.01
        return m

    def test_word_loop_supports_unlisted_order_and_repetition(self):
        m=self.model()
        values=[0]*10+[3]*10+[4]*10+[1]*10+[2]*10+[1]*10+[2]*10+[0]*30
        x=np.array([[v]*19 for v in values],dtype=float)
        self.assertEqual(m.decode(x)[0],['B','A','A'])
        online=OnlineWordHMM(m);words=[]
        for i,frame in enumerate(x):words.extend(online.push(frame,i*40)['words'])
        self.assertEqual(words,['B','A','A'])

    def test_holding_end_state_does_not_repeat_word(self):
        m=self.model();x=np.array([[v]*19 for v in [1]*10+[2]*100+[0]*20],dtype=float)
        self.assertEqual(m.decode(x)[0],['A'])

    def test_background_only_does_not_emit(self):
        online=OnlineWordHMM(self.model())
        events=[online.push(np.zeros(19),i*40) for i in range(100)]
        self.assertFalse(any(e['words'] for e in events))
        self.assertTrue(events[-1]['background_best'])
        self.assertFalse(events[-1]['pending_best'])

    def test_gap_resets_online_history(self):
        online=OnlineWordHMM(self.model());online.push(np.ones(19),0)
        with self.assertRaises(ValueError):online.push(np.ones(19),200)
        self.assertIsNone(online.scores)

    def test_feature_stream_matches_offline(self):
        ref={'flex_calibration':{k:{'open':1000,'closed':900} for k in FLEX_COLUMNS},
             'gravity':9.81,'gyro_bias':[0,0,0]}
        rows=[]
        for i in range(152):
            rows.append({'timestamp':i*10,**{k:950+10*np.sin(i*.1) for k in FLEX_COLUMNS},
                         **{k:float(np.cos(i*.1)) for k in ('ACCx','ACCy','ACCz','GYRx','GYRy','GYRz',*legacy.BODY_COLUMNS)}})
        builder=SensorFrames(ref)
        frames=[x for r in rows if (x:=builder.push(r)) is not None]
        np.testing.assert_allclose(frames,features(rows,ref),rtol=1e-5,atol=1e-5)
        row=dict(rows[-1],timestamp=1520,flex_2=0)
        with self.assertRaisesRegex(ValueError,'GPIO 33'):builder.push(row)
        self.assertFalse(builder.rows)


if __name__=='__main__':unittest.main()

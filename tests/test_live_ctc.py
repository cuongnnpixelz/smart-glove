import unittest
import numpy as np
import torch
from SmartSignLanguage.predict_word_ctc import LiveCTC, WindowCTC
from SmartSignLanguage.train_word_ctc import Network, LABELS, features, decode
from SmartSignLanguage.sequence_model_5 import FLEX_COLUMNS, legacy


class LiveCTCTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(3)
        self.model = Network().eval()
        self.ref = {'flex_calibration':{k:{'open':1000,'closed':900} for k in FLEX_COLUMNS},
                    'gravity':9.81,'gyro_bias':[.1,.2,.3]}
        self.checkpoint = {'schema':'causal-gru-ctc-five-flex-v1','labels':LABELS,
                           'mean':[.1]*19,'std':[2.]*19,'state_dict':self.model.state_dict()}
        self.rows = []
        for i in range(152):
            row = {'timestamp':i*10, **{k:950+10*np.sin(i*.1) for k in FLEX_COLUMNS}}
            row.update({k:float(np.sin(i*.03)) for k in ('ACCx','ACCy','ACCz','GYRx','GYRy','GYRz',*legacy.BODY_COLUMNS)})
            self.rows.append(row)

    def test_features_match_training_including_block_boundaries(self):
        live = LiveCTC(self.checkpoint,self.ref)
        actual = [v for row in self.rows if (v:=live.feature(row)) is not None]
        np.testing.assert_allclose(actual, features(self.rows,self.ref),rtol=1e-5,atol=1e-5)

    def test_stream_matches_whole_recording_decode(self):
        live = LiveCTC(self.checkpoint,self.ref)
        actual = [e['emitted'] for row in self.rows if (e:=live.push(row)) and e['emitted']]
        x = torch.tensor((features(self.rows,self.ref)-np.float32(.1))/np.float32(2))
        with torch.no_grad(): expected = decode(self.model(x[None])[0].argmax(-1).tolist())
        self.assertEqual(actual,expected)
        live.reset()
        self.assertIsNone(live.hidden)
        self.assertFalse(live.words)

    def test_gap_is_rejected(self):
        live = LiveCTC(self.checkpoint,self.ref)
        live.push(self.rows[0])
        with self.assertRaises(ValueError): live.push(self.rows[4])

    def test_window_uses_fresh_state_and_replaces_preview(self):
        live = WindowCTC(self.checkpoint,self.ref)
        rows = [dict(self.rows[i % len(self.rows)], timestamp=i*10) for i in range(325)]
        events = [event for row in rows if (event:=live.push(row)) is not None]
        self.assertEqual(len(events),2)
        x = torch.tensor((features(rows[-300:],self.ref)-np.float32(.1))/np.float32(2))
        with torch.no_grad(): expected = decode(self.model(x[None])[0].argmax(-1).tolist())
        self.assertEqual(events[-1]['preview'],expected)
        self.assertEqual(list(live.words),expected)
        self.assertIsNone(live.hidden)


if __name__ == '__main__': unittest.main()

import unittest
from unittest.mock import Mock
import numpy as np
import torch
from SmartSignLanguage.ctc_utterance import UtteranceCTC, token_peaks
from SmartSignLanguage.sequence_model_5 import FLEX_COLUMNS, legacy


class TurnTests(unittest.TestCase):
    def setUp(self):
        self.ref = {'flex_calibration':{k:{'open':1000,'closed':900} for k in FLEX_COLUMNS},
                    'gravity':9.81,'gyro_bias':[0,0,0]}
        self.detector = UtteranceCTC(None,np.zeros(19),np.ones(19),self.ref,
                                     {'flex':[0]*5,'gravity':[0,0,1]})
        self.detector.decode = Mock(return_value=(['TOI','KHOE'],[.9,.85]))
        self.clock = 0

    def feed(self, count, active=False, gyro=0, static_flex=None):
        events = []
        for _ in range(count):
            f = 940 if active else 1000
            if static_flex is not None: f=static_flex
            row = {'timestamp':self.clock, **{k:f for k in FLEX_COLUMNS},
                   'ACCx':0,'ACCy':0,'ACCz':9.81,'GYRx':gyro,'GYRy':0,'GYRz':0,
                   **{k:0 for k in legacy.BODY_COLUMNS}}
            self.clock += 10
            event = self.detector.push(row)
            if event: events.append(event)
        return events

    def test_no_per_word_rest_and_one_result_at_end(self):
        self.feed(100)
        self.assertEqual([e['state'] for e in self.feed(150,True)],['START'])
        # Brief transit near rest does not end a turn.
        self.assertFalse(self.feed(30))
        self.assertFalse(self.feed(150,True))
        events = self.feed(120)
        self.assertEqual([e['state'] for e in events],['RESULT'])
        self.assertEqual(events[0]['tokens'],['TOI','KHOE'])
        self.detector.decode.assert_called_once()
        self.assertFalse(self.feed(200))

    def test_static_sign_does_not_count_as_rest(self):
        self.feed(100)
        self.feed(100,True)
        self.assertFalse(self.feed(200,static_flex=940))
        self.assertEqual(self.detector.state,'ACTIVE')
        self.detector.decode.assert_not_called()

    def test_weak_and_empty_predictions_never_become_text(self):
        for result in [([],[]),(['BAN'],[.3])]:
            self.detector.reset()
            self.detector.decode.return_value = result
            self.feed(100); self.feed(100,True)
            events=self.feed(120)
            self.assertEqual(events[0]['state'],'UNCERTAIN')
            self.assertEqual(events[0]['tokens'],[])

    def test_short_incidental_motion_is_ignored(self):
        self.feed(100)
        self.assertFalse(self.feed(5,True))
        self.assertFalse(self.feed(120))
        self.detector.decode.assert_not_called()

    def test_long_turn_is_rejected_not_arbitrarily_cut_into_words(self):
        self.feed(100)
        events=self.feed(1000,True)
        self.assertEqual([e['state'] for e in events],['START','UNCERTAIN'])
        self.assertEqual(self.detector.state,'WAIT_REST')
        self.detector.decode.assert_not_called()
        self.assertEqual(self.feed(120)[0]['state'],'READY')

    def test_missing_data_discards_turn(self):
        self.feed(50,True); self.clock += 100
        with self.assertRaises(ValueError):self.feed(1,True)
        self.assertEqual(self.detector.state,'REST')
        self.assertFalse(self.detector.rows)

    def test_ctc_repeat_and_scores(self):
        logits = torch.full((5,6),-10.)
        for i,label in enumerate([1,1,0,1,2]): logits[i,label]=10
        words,scores=token_peaks(logits.log_softmax(-1))
        self.assertEqual(words,['TOI','TOI','CAM_ON'])
        self.assertEqual(len(scores),3)


if __name__=='__main__':unittest.main()

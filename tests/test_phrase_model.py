import unittest
from unittest.mock import Mock
import numpy as np
from SmartSignLanguage import phrase_model as backend
from SmartSignLanguage.phrase_data import make_phrase_reference
from SmartSignLanguage.predict_phrase_5 import PhraseDetector
from test_five_finger import rows, reference


def batch(start,count=300):
    sample=rows()[0]
    return [dict(sample,timestamp=start+i*10) for i in range(count)]


class PhraseModelTests(unittest.TestCase):
    def test_duration_normalization_preserves_static_shape(self):
        ref=make_phrase_reference(reference())
        a=backend.sequence_vector(batch(0),ref)
        b=backend.sequence_vector(batch(10000,500),ref)
        self.assertEqual(a.shape,(5700,))
        np.testing.assert_allclose(a,b,atol=1e-6)
        changed=batch(0);changed[-1]['flex_5']=4095
        with self.assertRaises(ValueError):backend.sequence_vector(changed,ref)

    def test_late_motion_is_not_discarded_at_150_samples(self):
        ref=make_phrase_reference(reference())
        original=batch(0)
        changed=batch(0)
        for row in changed[200:]:row['flex_1']-=100
        self.assertFalse(np.array_equal(backend.sequence_vector(original,ref),backend.sequence_vector(changed,ref)))

    def test_label_duration_mismatch_rejected(self):
        ref=make_phrase_reference(reference())
        ref['label_settings']={'CAU':{'seconds':5,'sample_count':500,'display_text':'Cau'}}
        with self.assertRaises(ValueError):backend.sequence_vector([dict(r,label='CAU') for r in batch(0)],ref)

    def test_rest_never_calls_classifier_even_if_it_would_predict_a_phrase(self):
        model=Mock(durations=[3.0]);model.predict.return_value='TOI_CAM_ON_BAN'
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        detector.update(batch(0,1000))
        model.predict.assert_not_called()
        self.assertEqual(detector.state,'ARMED')

    def test_no_result_until_full_duration_after_onset_and_one_result_only(self):
        model=Mock(durations=[3.0]);model.predict.return_value='CAU'
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        detector.update(batch(0,100))
        moving=[dict(r,GYRx=.8) for r in batch(1000,300)]
        event=detector.update(moving)
        self.assertEqual(event['state'],'WAIT')
        model.predict.assert_not_called()
        event=detector.update([dict(batch(4000,1)[0],GYRx=.8)])
        self.assertEqual(event,{'state':'RESULT','label':'CAU'})
        window=model.predict.call_args.args[0]
        self.assertEqual(len(window),300)
        self.assertEqual(window[0]['timestamp'],1000)
        self.assertEqual(window[-1]['timestamp'],3990)
        detector.update(batch(4010,500))
        self.assertEqual(model.predict.call_count,1)
        self.assertEqual(detector.state,'ARMED')
        detector.update([dict(r,GYRx=.8) for r in batch(9010,301)])
        self.assertEqual(model.predict.call_count,2)

    def test_light_motion_does_not_start_capture(self):
        for signal in ('gyro', 'flex', 'acc'):
            with self.subTest(signal=signal):
                model=Mock(durations=[3.0])
                detector=PhraseDetector(model,make_phrase_reference(reference()))
                detector.update(batch(0,100))
                moving=batch(1000,100)
                for row in moving:
                    if signal=='gyro': row['GYRx']=.45
                    elif signal=='flex': row['flex_1']-=.22*detector.spans[0]
                    else: row['ACCx']+=1.8
                detector.update(moving)
                self.assertEqual(detector.state,'ARMED')
                model.predict.assert_not_called()

    def test_brief_jerk_resets_confirmation_and_keeps_strong_onset(self):
        model=Mock(durations=[3.0])
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        detector.update(batch(0,100))
        detector.update([dict(r,GYRx=.8) for r in batch(1000,15)])
        self.assertEqual(detector.state,'ARMED')
        detector.update(batch(1150,10))
        detector.update([dict(r,GYRx=.8) for r in batch(1250,20)])
        self.assertEqual(detector.state,'ARMED')
        event=detector.update([dict(r,GYRx=.8) for r in batch(1450,1)])
        self.assertEqual(detector.state,'CAPTURE')
        self.assertIn('BAT DAU',event['reason'])
        self.assertEqual(detector.started,1250)
        self.assertEqual(len(detector.rows),21)
        detector.update(batch(1460,10))
        self.assertEqual(detector.state,'CAPTURE')
        self.assertEqual(len(detector.rows),31)

    def test_gap_discards_partial_episode_and_requires_new_rest(self):
        model=Mock(durations=[3.0]);model.predict.return_value='CAU'
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        detector.update(batch(0,100))
        detector.update([dict(r,GYRx=.8) for r in batch(1000,100)])
        self.assertEqual(detector.state,'CAPTURE')
        detector.update([dict(r,GYRx=.8) for r in batch(2500,400)])
        model.predict.assert_not_called()
        self.assertEqual(detector.state,'REST')
        with self.assertRaises(ValueError):detector.update(batch(0,1))

    def test_stationary_adc_saturation_is_error_not_motion(self):
        model=Mock(durations=[3.0])
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        event=detector.update([dict(r,flex_4=4095) for r in batch(0,100)])
        self.assertEqual(event['state'],'ERROR')
        model.predict.assert_not_called()

    def test_longest_duration_wait_and_aligned_short_window(self):
        model=Mock(durations=[3.0,5.0]);model.predict.return_value='CAU'
        detector=PhraseDetector(model,make_phrase_reference(reference()))
        detector.update(batch(0,100))
        detector.update([dict(r,GYRx=.8) for r in batch(1000,500)])
        model.predict.assert_not_called()
        self.assertEqual(detector.update(batch(6000,1))['state'],'RESULT')
        windows=[c.args[0] for c in model.predict.call_args_list]
        self.assertEqual([len(w) for w in windows],[300,500])
        self.assertTrue(all(w[0]['timestamp']==1000 for w in windows))


if __name__=='__main__':unittest.main()

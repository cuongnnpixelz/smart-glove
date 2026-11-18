import unittest
from unittest.mock import Mock
from SmartSignLanguage.ctc_utterance import rest_profile
from SmartSignLanguage.predict_word_ctc import acquire_rest
from SmartSignLanguage.sequence_model_5 import FLEX_COLUMNS, legacy


class RestTests(unittest.TestCase):
    def setUp(self):
        self.ref={'flex_calibration':{k:{'open':1000,'closed':949} for k in FLEX_COLUMNS},
                  'gravity':9.81,'gyro_bias':[0,0,0]}
        self.rows=[{'timestamp':i*10,**{k:1000+(i%17)-8 for k in FLEX_COLUMNS},
                    'ACCx':0,'ACCy':0,'ACCz':9.81,'GYRx':0,'GYRy':0,'GYRz':0,
                    **{k:0 for k in legacy.BODY_COLUMNS}} for i in range(100)]

    def test_small_span_noise_and_single_spike_allowed(self):
        self.rows[50]['flex_1']=1030
        self.assertIn('flex_noise_p90',rest_profile(self.rows,self.ref))

    def test_sustained_drift_rejected(self):
        for i,row in enumerate(self.rows):row['flex_1']=1000+i*.3
        with self.assertRaisesRegex(ValueError,'flex_1'):rest_profile(self.rows,self.ref)

    def test_gyro_motion_still_rejected(self):
        for row in self.rows:row['GYRx']=1
        with self.assertRaises(ValueError):rest_profile(self.rows,self.ref)

    def test_retry_preserves_calibration(self):
        moving=[dict(r,GYRx=1) for r in self.rows]
        stream=Mock();stream.capture.side_effect=[moving,self.rows]
        self.assertIsNotNone(acquire_rest(stream,self.ref))
        self.assertEqual(stream.capture.call_count,2)
        stream.configure_imu.assert_not_called()

    def test_connection_error_not_swallowed(self):
        stream=Mock();stream.capture.side_effect=OSError('disconnect')
        with self.assertRaises(OSError):acquire_rest(stream,self.ref)

    def test_user_can_quit_retries(self):
        stream=Mock();stream.capture.return_value=[dict(r,GYRx=1) for r in self.rows]
        self.assertIsNone(acquire_rest(stream,self.ref,prompt=lambda _: 'Q'))
        self.assertEqual(stream.capture.call_count,3)


if __name__=='__main__':unittest.main()

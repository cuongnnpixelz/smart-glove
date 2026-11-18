import io
import threading
import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage import predict_phrase_5 as app
from SmartSignLanguage.phrase_data import make_phrase_reference
from test_five_finger import reference
from test_phrase_model import batch


class PhraseReconnectTests(unittest.TestCase):
    def test_three_second_break_discards_motion_before_rearming(self):
        stream=Mock(condition=threading.Condition(),serial=0)
        clock=[0]
        def read(*args):
            clock[0]+=1
            if clock[0]>5:raise KeyboardInterrupt()
            return clock[0],[{'timestamp':clock[0]*1000}]
        stream.read_since.side_effect=read
        detector=Mock(duration_ms=3000,state='REST')
        detector.update.side_effect=[{'state':'RESULT','label':'CAU'},None]
        with patch.object(app,'PhraseDetector',return_value=detector), \
                patch.object(app.time,'monotonic',side_effect=lambda:clock[0]), \
                patch('sys.stdout',new_callable=io.StringIO) as output, \
                self.assertRaises(KeyboardInterrupt):
            app.recognize_live(stream,Mock(),{})
        self.assertEqual(detector.duration_ms,5000)
        self.assertEqual(detector.update.call_count,2)
        self.assertEqual(detector.update.call_args_list[1].args[0][0]['timestamp'],5000)
        for text in ('NGHI 3s','NGHI 2s','NGHI 1s','CHO SAN SANG'):
            self.assertIn(text,output.getvalue())

    def test_corrupted_partial_episode_never_reaches_model(self):
        stream=Mock(condition=threading.Condition(),serial=0)
        stream.read_since.side_effect=[(100,batch(0,100)),
            (300,[dict(r,GYRx=.8) for r in batch(1000,200)]),
            ValueError('RAW5_100 non ASCII 0xff')]
        model=Mock(durations=[3.0])
        with patch('sys.stdout',new_callable=io.StringIO), self.assertRaisesRegex(ValueError,'non ASCII'):
            app.recognize_live(stream,model,make_phrase_reference(reference()))
        model.predict.assert_not_called()

    def run_main(self, errors):
        model=Mock(manifest={'labels':['CAU','NONE']},durations=[3.0])
        streams=[Mock() for _ in errors]
        with patch.object(app,'PhraseModel',return_value=model), \
                patch.object(app,'SerialTransport'), \
                patch.object(app,'SampleStream',side_effect=streams), \
                patch.object(app,'calibrate',return_value=reference()) as calibration, \
                patch.object(app,'initialize_imu',return_value=reference()) as initialize, \
                patch.object(app,'recognize_live',side_effect=errors), \
                patch.object(app.time,'sleep'), \
                patch('sys.stdout',new_callable=io.StringIO) as output:
            status=app.main(['--model','unused','--recalibrate'])
        return status,streams,calibration,initialize,output.getvalue()

    def test_reconnect_reuses_flex_and_refreshes_imu(self):
        status,streams,calibration,initialize,output=self.run_main([
            ValueError('RAW5_100 non ASCII'),KeyboardInterrupt()])
        self.assertEqual(status,0)
        calibration.assert_called_once()
        initialize.assert_called_once()
        self.assertEqual(initialize.call_args.args[1]['flex_calibration'],reference()['flex_calibration'])
        for stream in streams:stream.close.assert_called_once()
        self.assertIn('DA NOI LAI',output)

    def test_repeated_errors_stop_after_three_reconnects(self):
        status,streams,calibration,initialize,output=self.run_main([
            ValueError('corrupt') for _ in range(4)])
        self.assertEqual(status,1)
        self.assertEqual(initialize.call_count,3)
        calibration.assert_called_once()
        for stream in streams:stream.close.assert_called_once()
        self.assertIn('sau 3 lan phuc hoi',output)

"""Continuous state/timing tests; synthetic streams are not hardware accuracy."""
import io
import threading
import unittest
from collections import deque
from unittest.mock import Mock, patch
import numpy as np

from SmartSignLanguage.continuous_sequence import ContinuousSegmenter
from SmartSignLanguage.sensor_pipeline import SamplingGap
from SmartSignLanguage.collect_v2 import SampleStream
from SmartSignLanguage import predict_continuous as app


def gesture(mode="correct"):
    t = np.arange(0,5001,40)
    bend = np.interp(t,[0,600,1100,3400,4300,5000],[0,0,1,1,.4,.4])
    angle = np.interp(t,[0,1500,2000,2600,3100,5000],[0,0,.8,.8,0,0])
    if mode == "tilt_only": bend[:]=0
    if mode == "hold": bend[t>3400]=1
    if mode == "not_returned": angle[t>2600]=.8
    speed = np.gradient(angle,.04)
    return [dict(flex_1=950.,flex_2=1050-100*b,Qw=np.cos(a/2),Qx=0.,Qy=np.sin(a/2),Qz=0.,
                 GYRx=0.,GYRy=v,GYRz=0.) for b,a,v in zip(bend,angle,speed)]


def stream_for(modes, final_rest=100):
    neutral = gesture()[0]
    stream = [neutral.copy() for _ in range(50)]
    for mode in modes:
        # An ADC offset between gestures is legitimate; release is only partial.
        offset = stream[-1]["flex_2"]-1050
        move = [dict(r,flex_2=r["flex_2"]+offset) for r in gesture(mode)]
        stream += move
        stream += [move[-1].copy() for _ in range(final_rest)]
    return [dict(r,timestamp=i*40) for i,r in enumerate(stream)]


class ContinuousTests(unittest.TestCase):
    def detector(self):
        predict = Mock(return_value=("TRO_TRAI_DUOI","TRO_TRAI_DUOI","test"))
        return ContinuousSegmenter({"gyro_bias":[0,0,0]},predict),predict

    def test_two_same_gestures_emit_once_each_with_partial_recovery_and_preroll(self):
        detector,predict = self.detector()
        events = [event for r in stream_for(["correct","correct"]) if (event:=detector.push(r))]
        results = [e for e in events if e["state"] == "RESULT"]
        self.assertEqual([r["label"] for r in results],["TRO_TRAI_DUOI"]*2)
        self.assertEqual(predict.call_count,2)
        for args in predict.call_args_list:
            window = args.args[0]
            self.assertGreaterEqual(window[-1]["timestamp"]-window[0]["timestamp"],5000)
            self.assertLessEqual(window[-1]["timestamp"]-window[0]["timestamp"],5120)
            self.assertLess(np.ptp([r["flex_2"] for r in window[:13]]),5)

    def test_stationary_and_tilt_only_do_not_emit_gesture(self):
        detector,predict = self.detector()
        results = [e for r in stream_for(["tilt_only"]) if (e:=detector.push(r)) and e["state"]=="RESULT"]
        self.assertTrue(results)
        self.assertTrue(all(e["label"]=="NONE" for e in results))
        predict.assert_not_called()
        detector,predict = self.detector()
        for i in range(1000): detector.push(dict(gesture()[0],timestamp=i*40))
        predict.assert_not_called()

    def test_held_finger_or_unreturned_wrist_never_rearms_until_release(self):
        for mode in ("hold","not_returned"):
            with self.subTest(mode=mode):
                detector,predict = self.detector()
                events = [e for r in stream_for([mode],final_rest=300) if (e:=detector.push(r))]
                self.assertEqual(detector.phase,"REST")
                self.assertEqual([e["label"] for e in events if e["state"]=="RESULT"],["NONE"])
                predict.assert_not_called()

    def test_wrong_finger_candidate_does_not_reach_lcd_result(self):
        detector,predict = self.detector()
        predict.return_value = ("GIUA_TRAI_DUOI","GIUA_TRAI_DUOI","wrong finger")
        results = [e for r in stream_for(["correct"]) if (e:=detector.push(r)) and e["state"]=="RESULT"]
        self.assertEqual(results[0]["label"],"NONE")

    def test_mid_gesture_gap_discards_window_without_prediction(self):
        detector,predict = self.detector()
        data = stream_for(["correct"])
        for r in data[:90]: detector.push(r)
        self.assertEqual(detector.phase,"TRACKING")
        with self.assertRaises(SamplingGap): detector.push(data[95])
        predict.assert_not_called()

    def test_read_since_no_duplicates_and_no_silent_overflow(self):
        stream = SampleStream.__new__(SampleStream)
        stream.condition = threading.Condition()
        stream.closed = threading.Event()
        stream.error = None
        stream.serial = 4
        stream.rows = deque([(3,{"timestamp":120}),(4,{"timestamp":160})])
        cursor,batch = stream.read_since(2,timeout=0)
        self.assertEqual(cursor,4)
        self.assertEqual(len(batch),2)
        self.assertEqual(stream.read_since(cursor,timeout=0),(4,[]))
        with self.assertRaises(ValueError): stream.read_since(1,timeout=0)
        stream.rows = deque([(3,{"timestamp":120}),(4,{"timestamp":1600})])
        with self.assertRaises(ValueError): stream.read_since(2,timeout=0)

    def test_runtime_initializes_without_input_and_forwards_final_decision(self):
        stream,model = Mock(),Mock()
        stream.condition = threading.Condition()
        stream.serial = 0
        stream.capture.return_value = []
        stream.read_since.side_effect = [(1,[{"timestamp":0}]),(2,[{"timestamp":40}]),KeyboardInterrupt()]
        detector = Mock()
        detector.push.side_effect = [{"state":"READY"},{"state":"RESULT","label":"TRO_PHAI_DUOI","candidate":"TRO_PHAI_DUOI","reason":"test"}]
        with patch.object(app,"make_imu_reference",return_value={"gyro_bias":[0,0,0]}), \
                patch.object(app,"ContinuousSegmenter",return_value=detector), \
                patch("builtins.input",side_effect=AssertionError("Must not prompt")), \
                patch("sys.stdout",new_callable=io.StringIO):
            with self.assertRaises(KeyboardInterrupt): app.run_connected(stream,model)
        packets = [c.args[0] for c in stream.sock.sendall.call_args_list]
        self.assertIn(b"RUN,CALIBRATING\n",packets)
        self.assertIn(b"RUN,READY\n",packets)
        self.assertIn(b"SEQ,TAM_BIET\n",packets)
        self.assertNotIn(b"START\n",packets)

    def test_gap_reconnects_with_new_stream_and_keyboard_interrupt_closes_it(self):
        first,second,model = Mock(),Mock(),Mock()
        model.motion_checks = "classifier-only"
        with patch.object(app,"SequenceModel",return_value=model), \
                patch.object(app.socket,"create_connection"), \
                patch.object(app,"SampleStream",side_effect=[first,second]), \
                patch.object(app,"run_connected",side_effect=[SamplingGap(1000),KeyboardInterrupt()]) as run, \
                patch.object(app.time,"sleep"), \
                patch("builtins.input",side_effect=AssertionError("Must not prompt")), \
                patch("sys.stdout",new_callable=io.StringIO):
            self.assertEqual(app.main(["--model","test-model"]),0)
        self.assertEqual(run.call_count,2)
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual([c.args[0] for c in first.sock.sendall.call_args_list],
                         [b"RUN,ERROR\n",b"RUN,OFF\n"])
        second.sock.sendall.assert_called_with(b"RUN,OFF\n")


if __name__ == "__main__": unittest.main()

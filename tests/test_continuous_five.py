"""Continuous five-finger windows, label updates, dropout handling and reconnect."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage import predict_continuous_5 as app
from test_five_finger import rows, reference, raw


def samples(start, count):
    template = rows()[0]
    return [dict(template, timestamp=(start+i)*10) for i in range(count)]


class ContinuousFiveTests(unittest.TestCase):
    def test_held_letter_repeats_without_rest_or_enter_and_uses_full_window(self):
        model = Mock()
        model.predict.return_value = "A"
        detector = app.SlidingRecognizer(model, reference())
        self.assertIsNone(detector.update(samples(0, 149)))
        self.assertEqual(detector.update(samples(149, 1))["state"], "WAIT")
        for start in (150, 175, 200):
            event = detector.update(samples(start, 25))
            self.assertEqual(event["label"], "A")
            self.assertEqual(event["state"], "RESULT")
        for call in model.predict.call_args_list:
            window = call.args[0]
            self.assertEqual(len(window), 150)
            self.assertEqual(window[-1]["timestamp"]-window[0]["timestamp"], 1490)
            self.assertIn("flex_5", window[0])

    def test_switches_directly_from_a_to_b_and_none_without_rest_gate(self):
        model = Mock()
        model.predict.side_effect = ["A", "A", "B", "B", "NONE", "NONE"]
        detector = app.SlidingRecognizer(model, reference())
        events = [detector.update(samples(0, 150))]
        events += [detector.update(samples(start, 25)) for start in range(150, 275, 25)]
        self.assertEqual([e.get("label") for e in events], [None, "A", None, "B", None, "NONE"])

    def test_gap_clears_old_samples_and_confirmation_before_next_result(self):
        model = Mock()
        model.predict.return_value = "D"
        detector = app.SlidingRecognizer(model, reference())
        detector.update(samples(0, 150))
        self.assertEqual(detector.update(samples(150, 25))["label"], "D")
        self.assertEqual(detector.update(samples(180, 1))["state"], "WAIT")
        self.assertEqual(len(detector.window), 1)
        before = model.predict.call_count
        self.assertIsNone(detector.update(samples(181, 148)))
        self.assertEqual(model.predict.call_count, before)
        self.assertEqual(detector.update(samples(329, 1))["state"], "WAIT")
        self.assertEqual(detector.update(samples(330, 25))["label"], "D")
        self.assertGreaterEqual(model.predict.call_args.args[0][0]["timestamp"], 1800)

    def test_bad_clock_or_clipped_flex_cannot_be_classified(self):
        model = Mock()
        detector = app.SlidingRecognizer(model, reference())
        batch = samples(0, 150)
        batch[-1]["flex_5"] = 4095
        self.assertEqual(detector.update(batch)["state"], "ERROR")
        model.predict.assert_not_called()
        with self.assertRaises(ValueError):
            detector.update(samples(0, 1))

    def test_imu_refresh_preserves_flex_calibration_and_never_prompts(self):
        ref = reference()
        old = json.dumps(ref, sort_keys=True)
        rest = [dict(raw(), timestamp=i*10, GYRx=.01) for i in range(301)]
        stream = Mock(error=None)
        stream.capture.side_effect = [rest, samples(301, 211)]
        stream.processor.ready = True
        with patch("builtins.input", side_effect=AssertionError("No Enter prompts")), \
                patch("sys.stdout", new_callable=io.StringIO):
            updated = app.initialize_imu(stream, ref)
        self.assertEqual(updated["flex_calibration"], ref["flex_calibration"])
        self.assertAlmostEqual(updated["gyro_bias"][0], .01)
        self.assertEqual(old, json.dumps(ref, sort_keys=True))
        stream.configure_imu.assert_called_once_with(updated)

    def test_lcd_protocol_has_no_invented_confidence(self):
        sock = Mock()
        app.send_result(sock, "A")
        sock.sendall.assert_called_with(b"LIVE,A\n")
        app.send_result(sock, "NONE")
        sock.sendall.assert_called_with(b"LIVE,NONE\n")
        app.send_state(sock, "ERROR")
        sock.sendall.assert_called_with(b"LIVE_STATE,ERROR\n")
        with self.assertRaises(ValueError):
            app.send_result(sock, "A\nSTART")

    def test_recognize_prints_repeated_results_until_interrupted(self):
        stream = Mock()
        stream.condition = threading.Condition()
        stream.serial = 0
        stream.read_since.side_effect = [
            (150, samples(0, 150)), (175, samples(150, 25)),
            (200, samples(175, 25)), KeyboardInterrupt()]
        model = Mock()
        model.predict.return_value = "C"
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            with self.assertRaises(KeyboardInterrupt):
                app.recognize(stream, model, reference())
        self.assertEqual(output.getvalue().count("KET QUA: C"), 2)
        results = [call.args[0] for call in stream.sock.sendall.call_args_list]
        self.assertEqual(results.count(b"LIVE,C\n"), 2)

    def test_reconnect_refreshes_imu_and_closes_both_connections(self):
        model = Mock(manifest={"labels": ["A", "NONE"], "evaluation_scope": "session_holdout"})
        streams = [Mock(), Mock()]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"reference.json"
            path.write_text(json.dumps(reference()), encoding="utf-8")
            with patch.object(app, "SequenceModel", return_value=model), \
                    patch.object(app.socket, "create_connection"), \
                    patch.object(app, "SampleStream", side_effect=streams) as factory, \
                    patch.object(app, "initialize_imu", return_value=reference()) as initialize, \
                    patch.object(app, "recognize", side_effect=[OSError("disconnect"), KeyboardInterrupt()]), \
                    patch.object(app.time, "sleep"), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(app.main(["--model", directory, "--reference", str(path)]), 0)
        self.assertEqual(initialize.call_count, 2)
        for call in factory.call_args_list:
            self.assertEqual(call.kwargs, {"flex_count": 5, "sample_ms": 10})
        for stream in streams:
            stream.close.assert_called_once()

    def test_short_stall_waits_and_discards_resumed_backlog(self):
        stream = Mock(condition=threading.Condition(), serial=0)
        stream.read_since.side_effect = [
            (0, []), (150, samples(0, 150)),
            (300, samples(150, 150)), (325, samples(300, 25)), KeyboardInterrupt()]
        model = Mock()
        model.predict.return_value = 'A'
        with patch.object(app.time, 'monotonic', side_effect=[0, .6, .6, .7, .8, .9]), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            with self.assertRaises(KeyboardInterrupt):
                app.recognize(stream, model, reference())
        self.assertIn('chua ngat ket noi', output.getvalue())
        self.assertEqual(model.predict.call_count, 2)
        self.assertEqual(model.predict.call_args_list[0].args[0][0]['timestamp'], 1500)

    def test_usb_recognition_opens_selected_port_and_closes_on_exit(self):
        model = Mock(manifest={'labels': ['A', 'NONE'], 'evaluation_scope': 'session_holdout'})
        stream = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'reference.json'
            path.write_text(json.dumps(reference()), encoding='utf-8')
            with patch.object(app, 'SequenceModel', return_value=model), \
                    patch.object(app, 'SerialTransport') as transport, \
                    patch.object(app.socket, 'create_connection') as wifi, \
                    patch.object(app, 'SampleStream', return_value=stream), \
                    patch.object(app, 'initialize_imu', return_value=reference()), \
                    patch.object(app, 'recognize', side_effect=KeyboardInterrupt()), \
                    patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(app.main(['--model', directory, '--reference', str(path),
                                           '--serial-port', 'COM3']), 0)
            transport.assert_called_once_with('COM3')
            wifi.assert_not_called()
            stream.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()

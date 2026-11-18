import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from SmartSignLanguage import check_word_trials as app


class WordTrialTests(unittest.TestCase):
    def test_fresh_window_only_and_stop_before_prediction(self):
        stream, model = Mock(), Mock()
        stream.start_trial.return_value = 123
        rows = [{'timestamp': i*10} for i in range(150)]
        stream.capture.return_value = rows
        model.predict.return_value = 'TOI'
        with patch.object(app, 'countdown'), patch.object(app, 'trial_quality'), patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(app.evaluate_trial(stream, model, {})[0], 'TOI')
        stream.capture.assert_called_once_with(1.5, sample_count=150, after=123)
        stream.sock.sendall.assert_called_once_with(b'STOP\n')
        model.predict.assert_called_once_with(rows, {})

    def test_bad_capture_never_predicts_and_stops(self):
        stream, model = Mock(), Mock()
        stream.capture.side_effect = ValueError('gap')
        with patch.object(app, 'countdown'), patch('sys.stdout',new_callable=io.StringIO):
            with self.assertRaises(ValueError):
                app.evaluate_trial(stream, model, {})
        model.predict.assert_not_called()
        stream.sock.sendall.assert_called_once_with(b'STOP\n')

    def test_wrong_prediction_counts_as_error_and_bad_performance_is_excluded(self):
        model = Mock(manifest={'labels':['TOI','CAM_ON']})
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'evaluate_trial',return_value=('TOI',[])), \
                patch('builtins.input',side_effect=['CAM_ON','','TOI','R','Q']), \
                patch('sys.stdout',new_callable=io.StringIO):
            app.run_trials(Mock(), model, {}, Path(tmp))
            result=json.loads((Path(tmp)/'summary.json').read_text())
            self.assertEqual((result['correct'],result['total'],result['attempts']),(0,1,2))
            self.assertEqual(len(list(Path(tmp).glob('trial_*.json'))),2)

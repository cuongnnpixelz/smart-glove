import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from SmartSignLanguage import collect_phrase_5 as app
from SmartSignLanguage.five_finger import CSV_COLUMNS
from test_five_finger import rows, reference


def batch(count, start=0):
    template = rows()[0]
    return [dict(template, timestamp=start+i*10) for i in range(count)]


class PhraseCollectionTests(unittest.TestCase):
    def run_collector(self, directory, answers, captures, extra_args=()):
        stream = Mock(error=None, recovery_required=None)
        stream.check_ready.return_value = {'hz': 100}
        stream.capture.side_effect = captures
        with patch.object(app, 'SerialTransport') as transport, \
                patch.object(app, 'SampleStream', return_value=stream), \
                patch.object(app, 'calibrate', return_value=reference()) as calibration, \
                patch.object(app, 'countdown'), \
                patch('builtins.input', side_effect=answers), \
                patch('sys.stdout', new_callable=io.StringIO):
            status = app.main(['--user-id', 'U02', '--serial-port', 'COM3',
                               '--output-dir', directory, '--repetitions', '1', *extra_args])
        transport.assert_called_once_with('COM3')
        calibration.assert_called_once()
        stream.close.assert_called_once()
        return status, stream

    def test_none_only_stops_at_30_saved_trials_and_retry_does_not_count(self):
        with tempfile.TemporaryDirectory() as directory:
            status, stream = self.run_collector(
                directory, ['', 'R'] + ['', ''] * 30,
                [batch(300, i * 4000) for i in range(31)],
                ['--none-only', '--repetitions', '30'])
            self.assertEqual(status, 0)
            self.assertEqual(stream.capture.call_count, 31)
            files = list(Path(directory).rglob('*.csv'))
            self.assertEqual([p.name for p in files], ['none.csv'])
            with files[0].open() as file:
                saved = list(csv.DictReader(file))
            self.assertEqual(len(saved), 9000)
            self.assertEqual({r['label'] for r in saved}, {'NONE'})
            self.assertEqual(len({r['trial_id'] for r in saved}), 30)
            self.assertEqual(int(saved[0]['timestamp']), 4000)

    def test_three_and_five_second_labels_and_retry_preserve_real_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            status, stream = self.run_collector(directory,
                ['toi cam on ban', '3s', '', '', 'R', '', '',
                 'cau dai', '5', '', '', '', '/Q'],
                [batch(300), batch(300, 4000), batch(500, 8000)])
            self.assertEqual(status, 0)
            folder = next(Path(directory).rglob('toi_cam_on_ban.csv')).parent
            ref = json.loads((folder/'imu_reference.json').read_text())
            self.assertEqual(ref['data_kind'], 'phrase')
            self.assertEqual(ref['user_id'], 'U02')
            self.assertEqual(ref['label_settings']['TOI_CAM_ON_BAN']['seconds'], 3)
            self.assertEqual(ref['label_settings']['CAU_DAI']['sample_count'], 500)
            for name, count, start, tid in [('toi_cam_on_ban', 300, 4000, '1'), ('cau_dai', 500, 8000, '2')]:
                with (folder/(name+'.csv')).open() as f:
                    reader = csv.DictReader(f)
                    saved = list(reader)
                    self.assertEqual(reader.fieldnames, list(CSV_COLUMNS))
                self.assertEqual(len(saved), count)
                self.assertEqual(int(saved[0]['timestamp']), start)
                self.assertEqual({r['trial_id'] for r in saved}, {tid})
                self.assertEqual({r['user_id'] for r in saved}, {'U02'})
            self.assertEqual(stream.capture.call_args_list[-1].kwargs['sample_count'], 500)
            self.assertFalse(list(Path(directory).rglob('Lan_*')))

    def test_menu_does_not_capture_and_bad_trial_is_not_saved(self):
        broken = batch(300)
        broken[-1]['flex_4'] = 4095
        with tempfile.TemporaryDirectory() as directory:
            status, stream = self.run_collector(directory,
                ['cau bo', '3', '', 'M', 'cau dung', '3', '', '', '', '', '/Q'],
                [broken, batch(300, 5000)])
            self.assertEqual(status, 0)
            self.assertEqual(stream.capture.call_count, 2)
            self.assertFalse(list(Path(directory).rglob('cau_bo.csv')))
            with next(Path(directory).rglob('cau_dung.csv')).open() as f:
                saved = list(csv.DictReader(f))
            self.assertEqual(len(saved), 300)
            self.assertEqual(saved[0]['trial_id'], '1')

    def test_repeated_label_keeps_duration_and_appends(self):
        with tempfile.TemporaryDirectory() as directory:
            status, _ = self.run_collector(directory,
                ['NONE', '3', '', '', '', 'NONE', '', '', '', '/Q'],
                [batch(300), batch(300, 4000)])
            self.assertEqual(status, 0)
            with next(Path(directory).rglob('none.csv')).open() as f:
                saved = list(csv.DictReader(f))
            self.assertEqual(len(saved), 600)
            self.assertEqual({r['trial_id'] for r in saved}, {'1', '2'})

    def test_port_closed_on_capture_failure_and_no_partial_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            status, _ = self.run_collector(directory,
                ['cau dai', '5', '', '', 'Q'], [OSError('Disconnected')])
            self.assertEqual(status, 0)
            self.assertFalse(list(Path(directory).rglob('*.csv')))

    def test_disconnect_continues_remaining_trials_without_flex_recalibration(self):
        first = Mock(error=None, recovery_required=None)
        second = Mock(error=None, recovery_required=None)
        first.check_ready.return_value = second.check_ready.return_value = {'hz':100}
        first.capture.side_effect = [batch(300, 10000), OSError('Disconnected')]
        second.capture.return_value = batch(300, 1000)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(app, 'SerialTransport'), \
                patch.object(app, 'SampleStream', side_effect=[first,second]), \
                patch.object(app, 'calibrate', return_value=reference()) as calibration, \
                patch.object(app, 'initialize_imu', return_value=reference()) as imu, \
                patch.object(app, 'countdown'), \
                patch('builtins.input', side_effect=['cau', '3', '2', '', '', '', '', '', '', '/Q']), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(app.main(['--output-dir',directory]),0)
            files=list(Path(directory).rglob('cau.csv'))
            self.assertEqual(len(files),2)
            sessions=set()
            for path in files:
                with path.open() as file:
                    saved=list(csv.DictReader(file))
                self.assertEqual(len(saved),300)
                self.assertEqual({r['trial_id'] for r in saved},{'1'})
                sessions.add(saved[0]['session_id'])
            self.assertEqual(len(sessions),2)
            refs=[json.loads(p.read_text()) for p in Path(directory).rglob('imu_reference.json')]
            self.assertEqual(sum('resumed_from' in r for r in refs),1)
        calibration.assert_called_once()
        imu.assert_called_once()
        first.close.assert_called_once()
        second.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()

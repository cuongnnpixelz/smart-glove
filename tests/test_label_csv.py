import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from SmartSignLanguage.session_csv import read_session, session_csv_groups, split_legacy_session, organize_session
from SmartSignLanguage.collect_sequence_5 import gesture_type, gesture_instruction
from SmartSignLanguage.collect_sequence import save_trial
from SmartSignLanguage.five_finger import CSV_COLUMNS, trial_quality
from SmartSignLanguage.train_sequence import load_trials
from SmartSignLanguage import sequence_model_5 as backend
from test_five_finger import rows, reference


class LabelCsvTests(unittest.TestCase):
    def test_split_preserves_every_field_and_training_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root/'data'/'U1'/'session'
            folder.mkdir(parents=True)
            ref = reference('s1')
            (folder/'imu_reference.json').write_text(json.dumps(ref), encoding='utf-8')
            for i in range(8):
                save_trial(folder/'samples.csv', rows(start=i*2000), 'U01', 's1', i+1,
                           'A' if i%2 else 'NONE', columns=CSV_COLUMNS, quality_check=trial_quality)
            original = (folder/'samples.csv').read_bytes()
            before = load_trials(root/'data', backend)[0]
            split_legacy_session(folder, root/'backup')
            self.assertFalse((folder/'samples.csv').exists())
            self.assertEqual({p.name for p in folder.glob('*.csv')}, {'a.csv', 'none.csv'})
            self.assertEqual(hashlib.sha256(original).digest(), hashlib.sha256((root/'backup'/'session'/'samples.csv').read_bytes()).digest())
            after, sources, _ = load_trials(root/'data', backend)
            self.assertEqual([r['key'] for r in before], [r['key'] for r in after])
            self.assertEqual({r['session'] for r in after}, {'s1'})
            self.assertEqual(len(sources), 2)
            for a, b in zip(before, after):
                self.assertEqual(a['label'], b['label'])
                self.assertTrue((a['vector'] == b['vector']).all())
            organize_session(folder)
            self.assertTrue((root/'data'/'U1'/'A'/'Lan_01'/'a.csv').exists())
            organized = load_trials(root/'data', backend)[0]
            self.assertEqual([t['key'] for t in after], [t['key'] for t in organized])
            for a, b in zip(after, organized):
                self.assertTrue((a['vector'] == b['vector']).all())

    def test_mixed_layout_and_wrong_label_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'imu_reference.json').write_text('{}')
            save_trial(folder/'b.csv', rows(), 'U01', 's1', 1, 'A', columns=CSV_COLUMNS, quality_check=trial_quality)
            with self.assertRaisesRegex(ValueError, 'khong khop'):
                read_session([folder/'b.csv'], CSV_COLUMNS)
            (folder/'samples.csv').write_text('')
            with self.assertRaisesRegex(ValueError, 'dem trung'):
                list(session_csv_groups(folder, per_label=True))

    def test_auto_mode_selects_motion_only_for_j_and_z(self):
        for label in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            self.assertEqual(gesture_type(label, 'auto'), 'dynamic' if label in 'JZ' else 'static')
        self.assertEqual(gesture_type('NONE', 'auto'), 'background')
        self.assertIn('ngon UT', gesture_instruction('J', 'auto'))
        self.assertIn('ngon TRO', gesture_instruction('Z', 'auto'))

import io
import unittest
from unittest.mock import patch

from SmartSignLanguage.train_sequence import TrainingProgress


class TrainingProgressTests(unittest.TestCase):
    def test_success_reports_elapsed_and_completion(self):
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            progress = TrainingProgress()
            with progress.stage('Train SVM'):
                pass
        self.assertIn('XONG: Train SVM', output.getvalue())
        self.assertIn('s]', output.getvalue())

    def test_failure_is_propagated_without_success_message(self):
        with patch('sys.stdout', new_callable=io.StringIO) as output:
            progress = TrainingProgress()
            with self.assertRaisesRegex(ValueError, 'bad data'):
                with progress.stage('Train SVM'):
                    raise ValueError('bad data')
        self.assertIn('Buoc bi dung', output.getvalue())
        self.assertNotIn('XONG:', output.getvalue())

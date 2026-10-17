"""Startup dependency checks, without GTK or audio files."""
from unittest.mock import patch
import unittest

from monkeygain.core import BackendStatus
from monkeygain.startup import check_runtime


class TestStartup(unittest.TestCase):
    @patch('monkeygain.startup.importlib.import_module', side_effect=ImportError('missing mutagen'))
    @patch('monkeygain.startup.probe_backend')
    def test_missing_metadata_dependency_prevents_main_window(self, backend, spec):
        result = check_runtime()
        self.assertFalse(result.ready)
        self.assertIn('python3-mutagen', result.message)
        backend.assert_not_called()

    @patch('monkeygain.startup.importlib.import_module', return_value=object())
    @patch('monkeygain.startup.probe_backend', return_value=BackendStatus(error='not found'))
    def test_missing_engine_prevents_main_window(self, backend, spec):
        result = check_runtime()
        self.assertFalse(result.ready)
        self.assertIn('rsgain', result.message)
        backend.assert_called_once_with()

    @patch('monkeygain.startup.importlib.import_module', return_value=object())
    @patch('monkeygain.startup.probe_backend', return_value=BackendStatus('/usr/bin/rsgain','3.4'))
    def test_ready_uses_detected_engine(self, backend, spec):
        result = check_runtime()
        self.assertTrue(result.ready)
        self.assertEqual(result.backend.path, '/usr/bin/rsgain')
        backend.assert_called_once_with()

    def test_main_window_source_has_no_manual_engine_controls(self):
        from pathlib import Path
        code = (Path(__file__).resolve().parents[1] / 'monkeygain/app.py').read_text()
        for control in ('Save Diagnostic Log…', 'About MonkeyGain', 'rsgain Executable',
                        'backend_entry', 'backend_row', 'engine_label', "'backend_path':"):
            self.assertNotIn(control, code)
        self.assertIn('check_runtime()', code)
        self.assertIn('if isinstance(window, MonkeyGainWindow):', code)


if __name__ == '__main__':
    unittest.main()

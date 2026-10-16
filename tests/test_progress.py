"""Regression tests for the progress-only GTK update, without a display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from monkeygain.activity import format_elapsed

SOURCE = Path(__file__).resolve().parents[1] / 'monkeygain' / 'app.py'


class DummyGLib:
    SOURCE_REMOVE = False
    SOURCE_CONTINUE = True


class FakeClock:
    @staticmethod
    def monotonic():
        return 145.6


class TestScanProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MonkeyGainWindow')
        method = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == '_tick_scan_progress')
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {'time': FakeClock, 'GLib': DummyGLib, 'format_elapsed': format_elapsed}
        exec(compile(module, str(SOURCE), 'exec'), namespace)
        cls.tick = staticmethod(namespace['_tick_scan_progress'])

    def test_activity_pulses_during_scan(self):
        progress = Mock()
        status = Mock()
        window = SimpleNamespace(
            _scan_started_at=75.0, _scan_progress_timer=1,
            _scan_completed_albums=1, _scan_active_album=1,
            _scan_cancel_requested=False,
            _jobs=[SimpleNamespace(label='Album A'), SimpleNamespace(label='Album B')],
            progress=progress, status_label=status,
            activity_timer_label=Mock(), _last_heartbeat_second=70,
            _append_activity=Mock(),
        )
        self.assertTrue(self.tick(window))
        progress.pulse.assert_called_once_with()
        progress.set_text.assert_called_once_with('1/2 albums · 1:10')
        status.set_text.assert_called_once_with('Scanning album 2/2: Album B · 1:10 elapsed')

    def test_elapsed_heartbeat_is_real_time_not_fake_percentage(self):
        progress = Mock()
        status = Mock()
        events = Mock()
        window = SimpleNamespace(
            _scan_started_at=125.0, _scan_progress_timer=1,
            _scan_completed_albums=0, _scan_active_album=0,
            _scan_cancel_requested=False,
            _jobs=[SimpleNamespace(label='Powerslave')],
            progress=progress, status_label=status,
            activity_timer_label=Mock(), _last_heartbeat_second=0,
            _append_activity=events,
        )
        self.assertTrue(self.tick(window))
        events.assert_called_once_with('working',
            'Analyzing Powerslave · still running', 20)
        self.assertEqual(window._last_heartbeat_second, 20)
        self.assertIn('0/1 albums', progress.set_text.call_args.args[0])

    def test_startup_pulses_before_album_notification(self):
        progress = Mock()
        status = Mock()
        window = SimpleNamespace(
            _scan_started_at=145.0, _scan_progress_timer=5,
            _scan_completed_albums=0, _scan_active_album=None,
            _scan_cancel_requested=False,
            _jobs=[SimpleNamespace(label='First')],
            progress=progress, status_label=status,
            activity_timer_label=Mock(), _last_heartbeat_second=0,
            _append_activity=Mock(),
        )
        self.assertTrue(self.tick(window))
        progress.pulse.assert_called_once_with()
        status.set_text.assert_not_called()

    def test_finished_stops_ticking(self):
        progress = Mock()
        window = SimpleNamespace(_scan_started_at=None, _scan_progress_timer=99, progress=progress)
        self.assertFalse(self.tick(window))
        self.assertIsNone(window._scan_progress_timer)
        progress.pulse.assert_not_called()

    def test_existing_loudness_behavior_is_unchanged(self):
        source = SOURCE.read_text(encoding='utf-8')
        self.assertIn("values['loudness'].set_text('—')", source)
        self.assertIn("stats['loudness'].set_text('—')", source)
        self.assertNotIn('Not stored', source)
        self.assertNotIn('LoudnessCache', source)


if __name__ == '__main__':
    unittest.main()

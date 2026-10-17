"""Regressions for restored album list without scroll-jumping timers."""
from pathlib import Path
import ast
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

APP = Path(__file__).resolve().parents[1] / 'monkeygain/app.py'
SOURCE = APP.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
WINDOW = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MonkeyGainWindow')

def method(name):
    node = next(n for n in WINDOW.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, node)

class AlbumListRestoreTests(unittest.TestCase):
    def test_revealer_owns_actual_details_widget(self):
        text = method('_make_album_row')
        self.assertIn('revealer.set_child(details)', text)
        self.assertIn('wrapper.append(revealer)', text)
        self.assertIn('self._build_track_details(row, job)', text)
        self.assertIn('revealer.set_reveal_child(active)', text)
        self.assertIn('Gtk.RevealerTransitionType.SLIDE_DOWN', text)

    def test_collapse_does_not_run_scroll_restoration_timers(self):
        text = method('_make_album_row')
        for forbidden in ('scroll_before_open', '_restore_closed_album_scroll',
                          'GLib.timeout_add(40', 'GLib.idle_add(self._restore_closed_album_scroll'):
            self.assertNotIn(forbidden, text)
        self.assertNotIn('def _restore_closed_album_scroll', SOURCE)

    def test_toggle_does_not_rebuild_album_page(self):
        text = method('_make_album_row')
        self.assertNotIn('self._render_page()', text)
        self.assertNotIn('self._update_collection()', text)
        self.assertIn('self._expanded_albums[job.folder] = active', text)

    def test_checkbox_highlight_preserves_row_geometry(self):
        self.assertIn("self._style_album_selection(row, job.folder in self._selection.selected)",
                      method('_make_album_row'))
        code=method('_style_album_selection')
        self.assertIn("row['widget']", code)
        self.assertNotIn('set_size_request', code)
        self.assertNotIn('set_visible', code)

    def test_results_still_use_existing_metrics(self):
        self.assertIn('self._apply_metrics(row, self._results.get(job.folder, {}))',
                      method('_make_album_row'))
        self.assertIn('TRACK', method('_build_track_details').upper())

if __name__ == '__main__':
    unittest.main()

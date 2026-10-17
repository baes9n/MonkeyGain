"""Static UI regression tests that run without a GTK display."""
from pathlib import Path
import unittest


APP = Path(__file__).resolve().parent.parent / 'monkeygain' / 'app.py'


class AlbumDisclosureTests(unittest.TestCase):
    def test_details_control_cannot_be_confused_with_play(self):
        source = APP.read_text(encoding='utf-8')
        section = source.split('    def _make_album_row(', 1)[1].split('    def _build_track_details(', 1)[0]
        self.assertIn("Gtk.Image.new_from_icon_name('view-list-symbolic')", section)
        self.assertNotIn("'pan-end-symbolic'", section)
        self.assertNotIn("'media-playback-start-symbolic'", section)

    def test_button_keeps_explicit_track_and_result_labels(self):
        source = APP.read_text(encoding='utf-8')
        section = source.split('    def _update_expander_caption(', 1)[1].split('    def _build_track_details(', 1)[0]
        for value in ('View results', 'Hide results', 'Show tracks', 'Hide tracks'):
            self.assertIn(value, section)


if __name__ == '__main__':
    unittest.main()

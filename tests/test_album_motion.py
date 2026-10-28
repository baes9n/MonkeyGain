"""Headless regression checks for album transitions and selection visibility."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'monkeygain/app.py').read_text(encoding='utf-8')
CSS = (ROOT / 'assets/style.css').read_text(encoding='utf-8')
TREE = ast.parse(APP)
WINDOW = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
              and node.name == 'MonkeyGainWindow')


def section(name):
    node = next(node for node in WINDOW.body
                if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(APP, node)


def isolated(name, bindings=None):
    node = next(node for node in WINDOW.body
                if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = dict(bindings or {})
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<MonkeyGain>', 'exec'), namespace)
    return namespace[name]


class FakeWidget:
    def __init__(self):
        self.classes = set()
        self.visible = None
    def add_css_class(self, name):
        self.classes.add(name)
    def remove_css_class(self, name):
        self.classes.discard(name)
    def set_visible(self, flag):
        self.visible = flag


class AlbumMotionTests(unittest.TestCase):
    def test_disclosure_matches_stable_list_behavior(self):
        code = section('_make_album_row')
        self.assertIn('Gtk.Revealer()', code)
        self.assertIn('Gtk.RevealerTransitionType.SLIDE_DOWN', code)
        self.assertIn('revealer.set_transition_duration(160)', code)
        self.assertIn('revealer.set_reveal_child(active)', code)
        self.assertIn('self._expanded_albums[job.folder] = active', code)

    def test_collapse_does_not_schedule_scroll_restoration(self):
        code = section('_make_album_row')
        self.assertNotIn('GLib.timeout_add(40, self._restore_closed_album_scroll', code)
        self.assertNotIn('GLib.idle_add(self._restore_closed_album_scroll', code)
        self.assertIn('revealer.set_reveal_child(active)', code)

    def test_no_obsolete_delayed_restoration_method(self):
        methods = {node.name for node in WINDOW.body if isinstance(node, ast.FunctionDef)}
        self.assertNotIn('_restore_closed_album_scroll', methods)
        self.assertNotIn('_finish_album_expand', methods)

    def test_selection_highlights_the_album_row(self):
        setter = isolated('_style_album_selection')
        row = {'widget': FakeWidget(), 'header': FakeWidget()}
        setter(row, True)
        self.assertIn('mg-selected-album', row['widget'].classes)
        setter(row, False)
        self.assertNotIn('mg-selected-album', row['widget'].classes)

    def test_selection_is_restored_when_paging(self):
        code = section('_make_album_row')
        self.assertIn('job.folder in self._selection.selected', code)
        self.assertIn('self._style_album_selection(row, job.folder in self._selection.selected)', code)
        self.assertIn('self._style_album_selection(row, active)', section('_toggle_selection'))
        self.assertIn('self._style_album_selection(row, True)', section('_select_matches'))
        self.assertIn('self._style_album_selection(row, False)', section('_clear_selection'))

    def test_theme_contrast_and_selected_visual_cues(self):
        for needle in ('.mg-dark row.mg-album-row.mg-selected-album',
                       '.mg-light row.mg-album-row.mg-selected-album',
                       'inset 4px 0',
                       '.mg-dark .mg-album-checkbox check:checked',
                       '.mg-light .mg-album-checkbox check:checked'):
            self.assertIn(needle, CSS)


if __name__ == '__main__':
    unittest.main()

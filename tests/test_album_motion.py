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
    def test_disclosure_uses_no_height_animation_or_focus_stealing(self):
        code = section('_make_album_row')
        self.assertIn('toggle.set_focus_on_click(False)', code)
        self.assertIn('Gtk.RevealerTransitionType.NONE', code)
        self.assertIn('revealer.set_transition_duration(0)', code)
        self.assertNotIn('Gtk.RevealerTransitionType.SLIDE_DOWN', code)
        self.assertNotIn('_finish_album_expand', code)

    def test_collapse_saves_and_restores_original_viewport(self):
        code = section('_make_album_row')
        self.assertIn("row['scroll_before_open'] = self.album_scroller.get_vadjustment().get_value()", code)
        self.assertIn('GLib.idle_add(self._restore_closed_album_scroll, row, previous)', code)
        self.assertIn('GLib.timeout_add(40, self._restore_closed_album_scroll, row, previous)', code)

    def test_delayed_restoration_ignores_removed_or_reopened_row(self):
        callback = isolated('_restore_closed_album_scroll',
                            {'GLib': types.SimpleNamespace(SOURCE_REMOVE=0)})
        row = {'folder': '/music/album',
               'toggle': types.SimpleNamespace(get_active=lambda: False)}
        self_obj = types.SimpleNamespace(_visible_rows={'/music/album': row},
                                         _restore_album_scroll=Mock())
        self.assertEqual(callback(self_obj, row, 250.0), 0)
        self_obj._restore_album_scroll.assert_called_once_with(250.0)
        self_obj._restore_album_scroll.reset_mock()
        row['toggle'] = types.SimpleNamespace(get_active=lambda: True)
        callback(self_obj, row, 250.0)
        self_obj._restore_album_scroll.assert_not_called()
        row['toggle'] = types.SimpleNamespace(get_active=lambda: False)
        self_obj._visible_rows = {}
        callback(self_obj, row, 250.0)
        self_obj._restore_album_scroll.assert_not_called()

    def test_selection_has_theme_independent_row_and_badge(self):
        setter = isolated('_style_album_selection')
        row = {'widget': FakeWidget(), 'header': FakeWidget(),
               'selected_label': FakeWidget()}
        setter(row, True)
        self.assertIn('mg-selected-album', row['widget'].classes)
        self.assertIn('mg-selected-album', row['header'].classes)
        self.assertTrue(row['selected_label'].visible)
        setter(row, False)
        self.assertNotIn('mg-selected-album', row['widget'].classes)
        self.assertNotIn('mg-selected-album', row['header'].classes)
        self.assertFalse(row['selected_label'].visible)

    def test_selection_is_restored_when_paging(self):
        code = section('_make_album_row')
        self.assertIn('job.folder in self._selection.selected', code)
        self.assertIn('self._style_album_selection(row, job.folder in self._selection.selected)', code)
        self.assertIn('self._style_album_selection(row, active)', section('_toggle_selection'))
        self.assertIn('self._style_album_selection(row, True)', section('_select_matches'))
        self.assertIn('self._style_album_selection(row, False)', section('_clear_selection'))

    def test_theme_contrast_and_expanded_visual_cues(self):
        for needle in ('.mg-dark row.mg-album-row.mg-selected-album',
                       '.mg-light row.mg-album-row.mg-selected-album',
                       '.mg-selected-badge',
                       'inset 4px 0',
                       'mg-expanded-album:not(.mg-selected-album)'):
            self.assertIn(needle, CSS)


if __name__ == '__main__':
    unittest.main()

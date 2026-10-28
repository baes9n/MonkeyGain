"""0.6.0 UI regression tests without a running GTK desktop."""
from pathlib import Path
import ast
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'monkeygain' / 'app.py').read_text(encoding='utf-8')
TREE = ast.parse(SRC)
WINDOW = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
              and node.name == 'MonkeyGainWindow')


def method_text(name):
    node = next(n for n in WINDOW.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, node)


def isolated_method(name, globals_dict=None):
    node = next(n for n in WINDOW.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = globals_dict or {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 str(ROOT/'monkeygain/app.py'), 'exec'), scope)
    return scope[name]


class FakeGdk:
    KEY_o, KEY_O, KEY_f, KEY_F, KEY_r, KEY_R = range(100, 106)
    KEY_Return, KEY_KP_Enter, KEY_Escape = range(106, 109)
    class ModifierType:
        CONTROL_MASK = 1
        SHIFT_MASK = 2
        MOD1_MASK = 4
        SUPER_MASK = 8


class UIRefinementTests(unittest.TestCase):
    def test_progress_is_hidden_after_import_and_scan(self):
        self.assertIn('self.progress.set_visible(False)', method_text('_end_import'))
        self.assertIn('self.progress.set_visible(False)', method_text('_on_finished'))
        self.assertIn('self.cancel_button.set_visible(False)', method_text('_end_import'))
        self.assertIn('self.cancel_button.set_visible(False)', method_text('_on_finished'))
        self.assertIn('self.progress.set_visible(True)', method_text('_discover'))
        self.assertIn('self.progress.set_visible(True)', method_text('_start'))
        self.assertIn('self.cancel_button.set_visible(True)', method_text('_discover'))
        self.assertIn('self.cancel_button.set_visible(True)', method_text('_start'))

    def test_one_progress_bar_no_console(self):
        self.assertEqual(SRC.count('self.progress = Gtk.ProgressBar()'), 1)
        self.assertNotIn('Gtk.TextView(', SRC)
        self.assertIn('self.selection_menu = Gtk.MenuButton()', SRC)
        self.assertIn("self.selection_menu.popdown()", method_text('_select_matches'))
        self.assertIn("self.selection_menu.popdown()", method_text('_clear_selection'))

    def test_compact_album_row_keeps_album_checkbox_and_results(self):
        section = method_text('_make_album_row')
        self.assertIn('Gtk.CheckButton()', section)
        self.assertIn("Gtk.Image.new_from_icon_name('view-list-symbolic')", section)
        self.assertIn('header.append(titles)', section)
        self.assertIn('header.append(toggle)', section)
        self.assertIn('self._style_album_selection(row, job.folder in self._selection.selected)', section)
        self.assertIn('self._update_expander_caption(row)', section)

    def test_keyboard_shortcuts_act_only_when_available(self):
        handler = isolated_method('_on_key_pressed', {'Gdk': FakeGdk})
        active = types.SimpleNamespace(get_sensitive=lambda: True)
        disabled = types.SimpleNamespace(get_sensitive=lambda: False)
        entry = types.SimpleNamespace(grab_focus=Mock(), has_focus=lambda: True,
                                      get_text=lambda: 'test', set_text=Mock())
        w = types.SimpleNamespace(add_folder_button=active, add_file_button=active,
                                  refresh_button=disabled, run_button=disabled,
                                  scan_all_button=active, search_entry=entry,
                                  _choose_folder=Mock(), _choose_files=Mock(),
                                  _refresh_tags=Mock(), _confirm_start=Mock())
        self.assertTrue(handler(w, None, FakeGdk.KEY_o, 0, 1))
        w._choose_files.assert_called_once()
        self.assertTrue(handler(w, None, FakeGdk.KEY_O, 0, 1 | 2))
        w._choose_folder.assert_called_once()
        self.assertTrue(handler(w, None, FakeGdk.KEY_Return, 0, 1))
        w._confirm_start.assert_not_called()  # Scan Selected is disabled
        self.assertTrue(handler(w, None, FakeGdk.KEY_Return, 0, 1 | 2))
        w._confirm_start.assert_called_once_with(True)
        self.assertTrue(handler(w, None, FakeGdk.KEY_f, 0, 1))
        entry.grab_focus.assert_called_once()
        self.assertTrue(handler(w, None, FakeGdk.KEY_Escape, 0, 0))
        entry.set_text.assert_called_once_with('')
        self.assertFalse(handler(w, None, FakeGdk.KEY_o, 0, 1 | 4))

    def test_album_row_keyboard_activation(self):
        activate = isolated_method('_on_album_activated')
        toggle = types.SimpleNamespace(get_active=lambda: False, set_active=Mock())
        w = types.SimpleNamespace(_rows=[{'widget': 'a', 'toggle': toggle}])
        activate(w, None, 'a')
        toggle.set_active.assert_called_once_with(True)
        activate(w, None, 'other')
        self.assertEqual(toggle.set_active.call_count, 1)


if __name__ == '__main__':
    unittest.main()

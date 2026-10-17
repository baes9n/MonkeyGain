"""UI/navigation regressions that do not require an X11/Wayland display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'monkeygain/app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
WINDOW = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'MonkeyGainWindow')

def method_source(name):
    node = next(n for n in WINDOW.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SOURCE, node)

def isolated(name, namespace):
    node = next(n for n in WINDOW.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {"Path": Path, **namespace}
    code = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(code, str(ROOT/'monkeygain/app.py'), 'exec'), scope)
    return scope[name]

class DummyGLib:
    SOURCE_REMOVE = False
    @staticmethod
    def idle_add(fn, *args):
        fn(*args)
        return 1

class ScanViewTests(unittest.TestCase):
    def test_scan_start_does_not_rebuild_list(self):
        source = method_source('_start')
        self.assertNotIn('self._update_collection()', source)
        self.assertNotIn('self._render_page()', source)
        self.assertIn('self._apply_metrics(row, {})', source)
        self.assertIn('self._follow_scan = True', source)

    def test_render_page_reuses_unmodified_rows(self):
        source = method_source('_render_page')
        self.assertIn('self._rendered_page_key == key', source)
        self.assertIn('return', source)
        self.assertIn('old_scroll', source)
        self.assertNotIn('get_vadjustment().set_value(0)', source)

    def test_active_album_on_next_page_is_found(self):
        focus = isolated('_focus_active_album', {'PAGE_SIZE': 40, 'GLib': DummyGLib})
        jobs = [SimpleNamespace(folder=f'/album/{n}') for n in range(85)]
        self_obj = SimpleNamespace(_follow_scan=True, _filtered_jobs=jobs, _page=0,
                                   _render_page=Mock(), _scroll_to_active_album=Mock())
        focus(self_obj, '/album/81')
        self.assertEqual(self_obj._page, 2)
        self_obj._render_page.assert_called_once()
        self_obj._scroll_to_active_album.assert_called_once_with('/album/81')

    def test_manual_navigation_disables_follow(self):
        focus = isolated('_focus_active_album', {'PAGE_SIZE': 40, 'GLib': DummyGLib})
        self_obj = SimpleNamespace(_follow_scan=False, _filtered_jobs=[], _page=0,
                                   _render_page=Mock(), _scroll_to_active_album=Mock())
        focus(self_obj, '/album/1')
        self_obj._render_page.assert_not_called()
        self_obj._scroll_to_active_album.assert_not_called()

    def test_hidden_filtered_album_is_not_forced_into_view(self):
        focus = isolated('_focus_active_album', {'PAGE_SIZE': 40, 'GLib': DummyGLib})
        self_obj = SimpleNamespace(_follow_scan=True,
                                   _filtered_jobs=[SimpleNamespace(folder='/album/2')],
                                   _page=0, _render_page=Mock(), _scroll_to_active_album=Mock())
        focus(self_obj, '/album/1')
        self_obj._render_page.assert_not_called()
        self_obj._scroll_to_active_album.assert_not_called()

    def test_auto_reveal_respects_user_and_last_result(self):
        reveal = isolated('_reveal_completed_results', {'GLib': DummyGLib})
        toggle = Mock()
        record = SimpleNamespace(_follow_scan=True, _last_active_folder='/last',
                                 _visible_rows={'/last': {'toggle': toggle}},
                                 _results={'/last': {'tracks': {'song': object()}}},
                                 _scroll_to_active_album=Mock())
        reveal(record)
        toggle.set_active.assert_called_once_with(True)
        record._follow_scan = False
        toggle.reset_mock()
        reveal(record)
        toggle.set_active.assert_not_called()

if __name__ == '__main__':
    unittest.main()

"""Per-user installation tests that never touch the real home folder."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from monkeygain.desktop import (
    APP_ID, DesktopPaths, desktop_contents, desktop_quote,
    destination_paths, install, launcher_contents, uninstall, installed_icons, ICON_SIZES, old_svg_icon,
)


class TestDesktop(unittest.TestCase):
    def test_paths_and_application_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = destination_paths(root, root / 'share')
            self.assertEqual(files.launcher, root / '.local/bin/monkeygain')
            self.assertEqual(files.entry.name, f'{APP_ID}.desktop')
            self.assertEqual(files.icon.name, f'{APP_ID}.png')
            self.assertEqual(APP_ID, 'io.github.baes9n.MonkeyGain')

    def test_launcher_preserves_arguments_and_spaces(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Music Developer's Projects"
            root.mkdir()
            (root / 'run.py').write_text('import sys\nprint(repr(sys.argv[1:]))\n')
            wrapper = Path(temp) / 'monkeygain'
            wrapper.write_text(launcher_contents(root, sys.executable))
            wrapper.chmod(0o755)
            result = subprocess.run([str(wrapper), 'First Track.flac', 'two;tracks.ogg'],
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "['First Track.flac', 'two;tracks.ogg']")

    def test_desktop_entry_includes_file_open_support(self):
        paths = DesktopPaths(Path('/home/music user/.local/bin/monkeygain'),
                             Path('/unused/app.desktop'), Path('/unused/icon.svg'))
        content = desktop_contents(paths)
        self.assertIn('Exec="/home/music user/.local/bin/monkeygain" %F\n', content)
        self.assertIn('Icon=io.github.baes9n.MonkeyGain\n', content)
        self.assertIn('Terminal=false\n', content)
        self.assertIn('Categories=AudioVideo;Audio;Utility;', content)

    def test_install_and_uninstall_keep_project_and_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / 'Git Source'
            (project / 'assets').mkdir(parents=True)
            (project / 'run.py').write_text('# the real application\n')
            (project / 'assets/icons').mkdir(parents=True)
            for size in ICON_SIZES:
                (project / 'assets/icons' / f'{size}.png').write_bytes(b'PNG_IMAGE')
            (project / '.git').mkdir()
            user = root / 'home'
            files = destination_paths(user, user / '.local/share')
            install(project, files, sys.executable)
            self.assertTrue(files.launcher.is_file())
            self.assertEqual(files.launcher.stat().st_mode & 0o777, 0o755)
            self.assertTrue(files.entry.is_file())
            self.assertEqual(files.icon.read_bytes(), b'PNG_IMAGE')
            self.assertTrue(all(icon.is_file() for icon in installed_icons(files)))
            self.assertIn(str(project / 'run.py'), files.launcher.read_text())
            removed = uninstall(files)
            self.assertEqual(set(removed), {files.entry, *installed_icons(files), files.launcher})
            self.assertTrue((project / '.git').is_dir())
            self.assertTrue((project / 'run.py').is_file())

    def test_uninstall_does_not_remove_unrelated_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            files = destination_paths(home, home / 'share')
            files.launcher.parent.mkdir(parents=True)
            files.launcher.write_text('#!/bin/sh\necho other-app\n')
            self.assertNotIn(files.launcher, uninstall(files))
            self.assertTrue(files.launcher.exists())


if __name__ == '__main__':
    unittest.main()

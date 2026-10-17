"""Headless tests of the Debian package staging and its desktop integration."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from build_deb import APP_ID, SIZES, build, read_version, stage


class TestDebPackaging(unittest.TestCase):
    def test_version_matches_source(self):
        self.assertEqual(read_version(ROOT), '0.5.5')

    def test_staging_has_icons_dependencies_and_independent_launcher(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stage(ROOT, root)
            launcher = root / 'usr/bin/monkeygain'
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
            text = launcher.read_text()
            self.assertIn('/usr/lib/monkeygain/run.py', text)
            self.assertIn('"$@"', text)
            self.assertNotIn('/data/Projects/', text)
            entry = (root / f'usr/share/applications/{APP_ID}.desktop').read_text()
            self.assertIn('Exec=/usr/bin/monkeygain %F', entry)
            self.assertIn(f'Icon={APP_ID}', entry)
            for size in SIZES:
                self.assertTrue((root / f'usr/share/icons/hicolor/{size}x{size}/apps/{APP_ID}.png').is_file())
            self.assertTrue((root / 'usr/lib/monkeygain/assets/style.css').is_file())
            for name in ('app', 'core', 'importer', 'metadata', 'selection', 'activity', 'desktop', 'startup'):
                self.assertTrue((root / f'usr/lib/monkeygain/monkeygain/{name}.py').is_file())
            control = (root / 'DEBIAN/control').read_text()
            self.assertIn('Architecture: all', control)
            self.assertIn('rsgain (>= 3.4)', control)
            self.assertIn('python3-mutagen', control)
            self.assertIn('Version: 0.5.5', control)
            self.assertTrue((root / 'usr/share/doc/monkeygain/copyright').is_file())

    @unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb unavailable')
    def test_deb_can_be_built_and_inspected(self):
        with tempfile.TemporaryDirectory() as td:
            path = build(ROOT, Path(td))
            self.assertTrue(path.is_file())
            info = subprocess.check_output(['dpkg-deb', '--field', str(path),
                                            'Package', 'Version', 'Architecture'], text=True)
            self.assertIn('monkeygain', info)
            self.assertIn('0.5.5', info)
            self.assertIn('all', info)
            listing = subprocess.check_output(['dpkg-deb', '--contents', str(path)], text=True)
            self.assertIn('usr/bin/monkeygain', listing)
            self.assertIn(f'{APP_ID}.desktop', listing)


if __name__ == '__main__':
    unittest.main()

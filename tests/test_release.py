"""Release packaging gate: field metadata and the installed payload."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from build_deb import build
from verify_release import PackageError, verify


@unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb unavailable')
class TestRelease(unittest.TestCase):
    def test_new_package_verifies_without_installing(self):
        with tempfile.TemporaryDirectory() as td:
            deb = build(ROOT, Path(td))
            self.assertEqual(verify(deb), '0.5.5')

    def test_bad_or_missing_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PackageError):
                verify(Path(td) / 'missing.deb')

    def test_missing_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            deb = build(ROOT, Path(td))
            original_run = __import__('verify_release').subprocess.run
            def omit_dependency(command, *args, **kwargs):
                result = original_run(command, *args, **kwargs)
                if command[:3] == ['dpkg-deb', '--field', str(deb)] and command[-1] == 'Depends':
                    result.stdout = 'python3, python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, python3-mutagen\n'
                return result
            with patch('verify_release.subprocess.run', side_effect=omit_dependency):
                with self.assertRaisesRegex(PackageError, 'rsgain'):
                    verify(deb)


if __name__ == '__main__':
    unittest.main()

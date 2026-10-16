from pathlib import Path
import tempfile
import unittest
from monkeygain.core import (
    AlbumJob, ScanSettings, build_command, discover_audio,
    make_album_jobs, backend_version,
)


class TestCore(unittest.TestCase):
    def test_discovery_multiformat_recursive_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'A').mkdir()
            (root / 'B').mkdir()
            (root / 'A' / '01.FLAC').touch()
            (root / 'A' / '02.mP3').touch()
            (root / 'B' / '03.opus').touch()
            (root / 'B' / 'readme.txt').touch()
            result = discover_audio([root, root / 'A' / '01.FLAC'])
            self.assertEqual(len(result), 3)
            jobs = make_album_jobs(result)
            self.assertEqual([len(x.files) for x in jobs], [2, 1])

    def test_rsgain_34_rejects_newer_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'audio.dsf').touch()
            (root / 'clip.webm').touch()
            self.assertEqual(discover_audio([root]), [])

    def test_default_command_matches_user_profile(self):
        job = AlbumJob(Path('/tmp/Album'), (Path('/tmp/Album/01.flac'), Path('/tmp/Album/02.mp3')))
        argv = build_command(ScanSettings(), job)
        self.assertEqual(argv, [
            'rsgain', 'custom', '--album', '--true-peak', '--loudness=-18',
            '--clip-mode=p', '--max-peak=-1', '--tagmode=i',
            '/tmp/Album/01.flac', '/tmp/Album/02.mp3',
        ])

    def test_dry_run(self):
        job = AlbumJob(Path('/tmp/Album'), (Path('/tmp/Album/01.flac'),))
        argv = build_command(ScanSettings(write_tags=False, skip_existing=True), job)
        self.assertIn('--tagmode=s', argv)
        self.assertIn('--skip-existing', argv)
        self.assertNotIn('--tagmode=i', argv)

    def test_validates_loudness(self):
        job = AlbumJob(Path('/tmp/Album'), (Path('/tmp/Album/01.flac'),))
        with self.assertRaises(ValueError):
            build_command(ScanSettings(loudness=-40), job)

    def test_missing_backend_is_graceful(self):
        self.assertIsNone(backend_version('nonexistent_rsgain_binary_5F328'))


if __name__ == '__main__':
    unittest.main()

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
            '--clip-mode=p', '--max-peak=-1', '--tagmode=i', '--output',
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


class TestBackendProbe(unittest.TestCase):
    def test_detect_manual_path_and_version(self):
        from monkeygain.core import probe_backend
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'rsgain'
            fake.write_text('#!/bin/sh\nprintf "rsgain 3.4 - using:\\n"\n', encoding='utf-8')
            fake.chmod(0o755)
            result = probe_backend(str(fake))
            self.assertEqual(result.version, '3.4')
            self.assertEqual(result.path, str(fake))
            self.assertFalse(result.error)

    def test_detect_version_with_rsgain_ansi_colors(self):
        from monkeygain.core import probe_backend
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'rsgain'
            # The actual v3.4 CLI wraps its program name in ANSI colors.
            fake.write_text('#!/bin/sh\nprintf "\\033[1;32mrsgain\\033[0m 3.4 - using:\n"\n', encoding='utf-8')
            fake.chmod(0o755)
            result = probe_backend(str(fake))
            self.assertEqual(result.version, '3.4')

    def test_detect_non_executable_error(self):
        from monkeygain.core import probe_backend
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'rsgain'
            fake.write_text('not executable', encoding='utf-8')
            fake.chmod(0o644)
            result = probe_backend(str(fake))
            self.assertIsNone(result.path)
            self.assertIn('not executable', result.error)

    def test_manual_path_does_not_silently_fallback(self):
        from monkeygain.core import probe_backend
        result = probe_backend('/nonexistent/path/to/rsgain')
        self.assertIsNone(result.path)
        self.assertIn('/nonexistent/path/to/rsgain', result.error)

    def test_runner_executes_resolved_binary_with_spaced_path(self):
        from monkeygain.core import ScanRunner
        with tempfile.TemporaryDirectory(prefix='monkey gain ') as tmp:
            exe = Path(tmp) / 'fake rsgain'
            output = Path(tmp) / 'args.txt'
            exe.write_text(
                '#!/bin/sh\n'
                'printf "%s\\n" "$@" > "' + str(output) + '"\n',
                encoding='utf-8',
            )
            exe.chmod(0o755)
            album = Path(tmp) / 'My Album'
            album.mkdir()
            song = album / '01 song.flac'
            song.touch()
            events = []
            runner = ScanRunner(lambda line: events.append(line),
                                lambda index, state: events.append(state),
                                lambda ok, err, cancelled: events.append((ok, err, cancelled)))
            runner.start([AlbumJob(album, (song,))], ScanSettings(write_tags=False), str(exe))
            runner._thread.join(timeout=5)
            self.assertFalse(runner.running)
            args = output.read_text(encoding='utf-8').splitlines()
            self.assertEqual(args[0], 'custom')
            self.assertEqual(args[-1], str(song))
            self.assertIn('--tagmode=s', args)
            self.assertIn((1, 0, False), events)


if __name__ == '__main__':
    unittest.main()

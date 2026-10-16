"""Regression tests for rsgain 3.4 tab-separated results and worker events."""
from pathlib import Path
import tempfile
import unittest

from monkeygain.core import (AlbumJob, ScanSettings, ScanRunner, build_command,
                             parse_metric, current_track_from_log)


class TestResults(unittest.TestCase):
    def setUp(self):
        self.job = AlbumJob(Path('/tmp/Metal Album'), (
            Path('/tmp/Metal Album/01 - Track.flac'),
            Path('/tmp/Metal Album/02 - Track.mp3'),
        ))

    def test_output_option_is_included_in_safe_arguments(self):
        command = build_command(ScanSettings(), self.job)
        self.assertIn('--output', command)
        self.assertNotIn('*.flac', ' '.join(command))
        self.assertEqual(command[-2:], [str(p) for p in self.job.files])

    def test_tsv_track_row(self):
        line = '01 - Track.flac\t-13.30\t-4.70\t0.996735\t-0.03\tTrue\tN\n'
        metric = parse_metric(line, self.job)
        self.assertIsNotNone(metric)
        self.assertEqual(metric.filename, '01 - Track.flac')
        self.assertEqual(metric.gain, -4.7)
        self.assertAlmostEqual(metric.peak, .996735)
        self.assertFalse(metric.is_album)

    def test_tsv_album_and_infinite_silence(self):
        metric = parse_metric('Album\t-∞\t0.00\t0.000000\t-∞\tSample\tY\n', self.job)
        self.assertTrue(metric.is_album)
        self.assertEqual(metric.loudness, float('-inf'))
        self.assertTrue(metric.clipping_adjusted)

    def test_rejects_unrelated_lines(self):
        self.assertIsNone(parse_metric('Filename\tLoudness (LUFS)\tGain (dB)\tPeak\t Peak (dB)\tPeak Type\tClipping Adjustment?\n', self.job))
        self.assertIsNone(parse_metric('unknown.flac\t-10\t-8\t1\t0\tTrue\tN\n', self.job))
        self.assertIsNone(parse_metric('Album\t-10\t???\t1\t0\tTrue\tN\n', self.job))

    def test_progress_line_exact_file_path(self):
        self.assertEqual(current_track_from_log("[OK] Scanning '/tmp/Metal Album/01 - Track.flac'\n", self.job), '01 - Track.flac')
        self.assertIsNone(current_track_from_log("Scanning '/other/directory/01 - Track.flac'\n", self.job))

    def test_fake_scan_emits_real_structured_metrics(self):
        with tempfile.TemporaryDirectory(prefix='MonkeyGain test ') as tmp:
            folder = Path(tmp)
            track = folder / 'my song.flac'
            track.touch()
            fake = folder / 'rsgain mock'
            fake.write_text(
                '#!/bin/sh\n'
                'printf "Filename\\tLoudness (LUFS)\\tGain (dB)\\tPeak\\t Peak (dB)\\tPeak Type\\tClipping Adjustment?\\n"\n'
                'printf "my song.flac\\t-15.30\\t-2.70\\t0.960000\\t-0.35\\tTrue\\tN\\n"\n'
                'printf "Album\\t-15.30\\t-2.70\\t0.960000\\t-0.35\\tTrue\\tN\\n"\n',
                encoding='utf-8',
            )
            fake.chmod(0o755)
            metrics, finishes, logs = [], [], []
            runner = ScanRunner(logs.append, lambda *_: None,
                                lambda *args: finishes.append(args),
                                lambda _index, metric: metrics.append(metric))
            runner.start([AlbumJob(folder, (track,))], ScanSettings(write_tags=False), str(fake))
            runner._thread.join(5)
            self.assertFalse(runner.running)
            self.assertEqual(finishes, [(1, 0, False)])
            self.assertEqual(len(metrics), 2)
            self.assertFalse(metrics[0].is_album)
            self.assertTrue(metrics[1].is_album)
            self.assertIn('--output', ''.join(logs))


if __name__ == '__main__':
    unittest.main()

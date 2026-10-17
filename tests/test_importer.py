"""Headless tests for bounded navigation, progress and cancellation."""
from __future__ import annotations
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from monkeygain.importer import (ImportRunner, ImportUpdate, iter_audio_files,
                                 page_bounds, PAGE_SIZE, TRACKS_PER_BATCH, matches_tag_filter, group_imported_paths)
from monkeygain.metadata import TagRead, ExistingGain


class ImporterTests(unittest.TestCase):
    def test_group_imported_paths_avoids_filesystem_access(self):
        files = [Path('/music/A/02.flac'), Path('/music/B/01.mp3'),
                 Path('/music/A/01.flac')]
        with patch.object(Path, 'resolve', side_effect=AssertionError('must not resolve')):
            with patch.object(Path, 'is_file', side_effect=AssertionError('must not stat')):
                jobs = group_imported_paths(files)
        self.assertEqual(len(jobs), 2)
        self.assertEqual([x.name for x in jobs[0].files], ['01.flac', '02.flac'])

    def test_tag_filters_do_not_change_the_album_queue(self):
        tagged = TagRead(ExistingGain(track_gain=-3.0))
        plain = TagRead()
        broken = TagRead(error='bad header')
        self.assertTrue(matches_tag_filter([tagged, tagged], 1))
        self.assertFalse(matches_tag_filter([tagged, plain], 1))
        self.assertTrue(matches_tag_filter([tagged, plain], 2))
        self.assertFalse(matches_tag_filter([tagged, tagged], 2))
        self.assertTrue(matches_tag_filter([broken, tagged], 3))
        self.assertFalse(matches_tag_filter([plain], 3))
        self.assertTrue(matches_tag_filter([broken], 0))

    def test_page_bounds(self):
        self.assertEqual(page_bounds(0, 0), (0, 0, 0))
        self.assertEqual(page_bounds(1000, 0), (0, 0, PAGE_SIZE))
        self.assertEqual(page_bounds(1000, 24), (24, 960, 1000))
        self.assertEqual(page_bounds(1000, 99), (24, 960, 1000))
        self.assertEqual(page_bounds(1000, -10), (0, 0, PAGE_SIZE))
        self.assertEqual(page_bounds(1000, 5, 60), (5, 300, 360))
        with self.assertRaises(ValueError):
            page_bounds(2, 0, 0)

    def test_cancel_discovery_does_not_follow_symlink_directories(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            (root / 'album').mkdir()
            (root / 'album' / 'a.flac').touch()
            (root / 'album' / 'b.mp3').touch()
            (root / 'album' / 'ignore.txt').touch()
            (root / 'link').symlink_to(root / 'album', target_is_directory=True)
            result = list(iter_audio_files([root, root / 'album' / 'a.flac'], threading.Event()))
            self.assertEqual({p.name for p in result}, {'a.flac', 'b.mp3'})
            cancelled = threading.Event()
            cancelled.set()
            self.assertEqual(list(iter_audio_files([root], cancelled)), [])

    def test_large_library_imports_in_batches_and_all_files_remain(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            for album in range(100):
                folder = root / f'Album-{album:03}'
                folder.mkdir()
                for track in range(50):
                    (folder / f'{track:02}.flac').touch()
            events = []
            def fake_loader(batch):
                return {file: TagRead() for file in batch}
            with patch('monkeygain.importer.load_existing_tags', side_effect=fake_loader):
                runner = ImportRunner(events.append, batch_size=80)
                runner.start([root])
                runner._thread.join(timeout=25)
            self.assertFalse(runner.running)
            self.assertEqual(events[-1].phase, 'complete')
            self.assertEqual(events[-1].discovered, 5000)
            self.assertEqual(events[-1].inspected, 5000)
            self.assertEqual(sum(len(e.files) for e in events), 5000)
            progress = [e.inspected for e in events if e.phase == 'reading']
            self.assertEqual(progress, sorted(progress))
            self.assertTrue(all(len(e.files) <= 80 for e in events))
            self.assertGreater(len([e for e in events if e.files]), 60)
            self.assertLessEqual(PAGE_SIZE, 40)
            self.assertLessEqual(TRACKS_PER_BATCH, 60)

    def test_cancel_between_batches_preserves_completed_work(self):
        with tempfile.TemporaryDirectory() as base:
            root = Path(base)
            for index in range(120):
                (root / f'{index:03}.flac').touch()
            events = []
            runner = ImportRunner(lambda e: (events.append(e),
                            runner.cancel() if e.phase == 'reading' and e.inspected >= 15 else None),
                            batch_size=15)
            with patch('monkeygain.importer.load_existing_tags',
                       side_effect=lambda batch: {p: TagRead() for p in batch}):
                runner.start([root])
                runner._thread.join(timeout=10)
            self.assertEqual(events[-1].phase, 'cancelled')
            self.assertEqual(events[-1].inspected, 15)
            self.assertEqual(sum(len(e.files) for e in events), 15)


if __name__ == '__main__':
    unittest.main()

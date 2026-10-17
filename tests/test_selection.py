"""Headless tests for album selection, filters, and scan scope."""
from __future__ import annotations

from pathlib import Path
import unittest

from monkeygain.core import AlbumJob
from monkeygain.importer import group_imported_paths, matches_album, page_bounds
from monkeygain.selection import AlbumSelection, plan_scan, plan_result_reveal


class AlbumSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = group_imported_paths(
            Path(f'/music/Artist/Album-{n:03}/track.flac') for n in range(105))
        cls.by_folder = {job.folder: job for job in cls.jobs}

    def test_no_album_selected_by_default(self):
        model = AlbumSelection()
        self.assertEqual(model.count(), 0)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False), [])

    def test_scan_all_ignores_empty_selection(self):
        model = AlbumSelection()
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=True), self.jobs)

    def test_select_album_from_other_page(self):
        model = AlbumSelection()
        folder = self.jobs[80].folder
        model.toggle(folder, True)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False), [self.jobs[80]])
        self.assertEqual(page_bounds(len(self.jobs), 2), (2, 80, 105))
        model.toggle(folder, False)
        self.assertEqual(model.count(), 0)

    def test_bulk_select_filtered_albums_across_pages(self):
        model = AlbumSelection()
        filtered = [job for job in self.jobs if job.label.startswith('Album-0')]
        self.assertEqual(len(filtered), 100)
        model.select(job.folder for job in filtered)
        self.assertEqual(model.count(), 100)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False), filtered)

    def test_search_does_not_implicitly_change_selection(self):
        model = AlbumSelection()
        model.toggle(self.jobs[60].folder, True)
        matches = [job for job in self.jobs if matches_album('album-008', job.label,
                                                               job.folder.parent.name,
                                                               (p.stem for p in job.files))]
        self.assertEqual(len(matches), 1)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False), [self.jobs[60]])
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=True), self.jobs)

    def test_select_matches_unions_with_existing_selection(self):
        model = AlbumSelection()
        model.toggle(self.jobs[60].folder, True)
        model.select(job.folder for job in self.jobs[:5])
        self.assertEqual(model.count(), 6)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False),
                         self.jobs[:5] + [self.jobs[60]])

    def test_prune_dropped_album_after_removal(self):
        model = AlbumSelection()
        model.select([self.jobs[0].folder, self.jobs[5].folder, self.jobs[50].folder])
        model.prune([job.folder for job in self.jobs if job.folder != self.jobs[5].folder])
        self.assertEqual(model.count(), 2)
        self.assertNotIn(self.jobs[5].folder, model.selected)

    def test_clear_selection_does_not_remove_jobs(self):
        model = AlbumSelection()
        model.select(job.folder for job in self.jobs)
        model.clear()
        self.assertEqual(model.count(), 0)
        self.assertEqual(len(self.jobs), 105)
        self.assertEqual(len(plan_scan(self.jobs, model.selected, all_albums=True)), 105)

    def test_album_order_preserved_independent_of_click_order(self):
        model = AlbumSelection()
        for i in (98, 3, 26, 2):
            model.toggle(self.jobs[i].folder, True)
        self.assertEqual(plan_scan(self.jobs, model.selected, all_albums=False),
                         [self.jobs[i] for i in (2, 3, 26, 98)])

    def test_search_finds_artist_album_and_track(self):
        job = AlbumJob(Path('/music/Iron Maiden/Powerslave'),
                       (Path('/music/Iron Maiden/Powerslave/01 Aces High.flac'),))
        self.assertTrue(matches_album('iron maiden', job.label, job.folder.parent.name,
                                      (p.stem for p in job.files)))
        self.assertTrue(matches_album('aces high', job.label, job.folder.parent.name,
                                      (p.stem for p in job.files)))
        self.assertTrue(matches_album('power', job.label, job.folder.parent.name,
                                      (p.stem for p in job.files)))
        self.assertFalse(matches_album('painkiller', job.label, job.folder.parent.name,
                                       (p.stem for p in job.files)))


class ResultVisibilityTests(unittest.TestCase):
    """The UI must restore results without rendering an entire large queue."""

    @classmethod
    def setUpClass(cls):
        cls.folders = [Path(f'/Music/Album-{n}') for n in range(8)]

    def test_single_visible_completed_album_expands(self):
        album = self.folders[1]
        self.assertEqual(plan_result_reveal([album], {album}, {album}, set()), [album])

    def test_auto_expansion_is_limited_to_two(self):
        folders = self.folders
        self.assertEqual(plan_result_reveal(folders, set(folders), set(folders), set()), folders[:2])

    def test_scanned_hidden_or_failed_albums_are_never_autoexpanded(self):
        folders = self.folders
        # First is filtered out, second has no output, third has results.
        self.assertEqual(plan_result_reveal(folders[:4], set(folders[1:4]),
                                            {folders[0], folders[2]}, set()), [folders[2]])

    def test_already_open_album_counts_towards_render_budget(self):
        folders = self.folders
        self.assertEqual(plan_result_reveal(folders, set(folders), set(folders),
                                            {folders[0]}), [folders[1]])

    def test_only_just_scanned_albums_can_expand(self):
        folders = self.folders
        self.assertEqual(plan_result_reveal(folders[3:5], set(folders), set(folders),
                                            set()), folders[3:5])

    def test_zero_limit_disables_auto_expansion(self):
        folders = self.folders
        self.assertEqual(plan_result_reveal(folders, set(folders), set(folders),
                                            set(), limit=0), [])


if __name__ == '__main__':
    unittest.main()

"""Scanner activity is not represented as fictional per-track progress."""
import unittest

from monkeygain.activity import ActivityEvent, ActivityJournal, format_elapsed


class TestActivityJournal(unittest.TestCase):
    def test_elapsed(self):
        self.assertEqual(format_elapsed(0), '0:00')
        self.assertEqual(format_elapsed(9), '0:09')
        self.assertEqual(format_elapsed(72.9), '1:12')
        self.assertEqual(format_elapsed(3701), '1:01:41')
        self.assertEqual(format_elapsed(-4), '0:00')

    def test_event_timestamps_and_levels(self):
        self.assertEqual(ActivityEvent('working', 'Analyzing album', 10).display(),
                         '[0:10]  ◌  Analyzing album\n')
        self.assertEqual(ActivityEvent('success', 'Done').display(),
                         '         ✓  Done\n')

    def test_raw_is_independent_of_friendly_entries(self):
        journal = ActivityJournal()
        journal.add('working', 'Analyzing', 0)
        journal.add_raw('$ rsgain custom --output ...\n')
        journal.add_raw('Album\t-17.51\t-0.49\t0.95\t-0.44\tTrue\tN\n')
        self.assertEqual(len(journal.events), 1)
        self.assertEqual(journal.raw_text(),
                         '$ rsgain custom --output ...\nAlbum\t-17.51\t-0.49\t0.95\t-0.44\tTrue\tN\n')
        journal.clear()
        self.assertEqual(journal.raw_text(), '')
        self.assertEqual(journal.events, [])


if __name__ == '__main__':
    unittest.main()

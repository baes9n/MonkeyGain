"""Tests for safe, format-aware reading of existing gain tags."""
from pathlib import Path
from unittest.mock import patch
import math
import tempfile
import unittest

from monkeygain.metadata import (
    ExistingGain, _fields, _float_value, _int_r128, common_album_value,
    linear_peak_db, read_existing_gain, load_existing_tags,
)


class MockAudio:
    def __init__(self, tags):
        self.tags = tags


class TXXX:
    def __init__(self, text):
        self.text = [text]


class TestMetadata(unittest.TestCase):
    def test_numbers_and_missing_values(self):
        self.assertEqual(_float_value('-4.70 dB'), -4.7)
        self.assertEqual(_float_value(b'0.996735'), 0.996735)
        self.assertIsNone(_float_value('not a value'))
        self.assertIsNone(_float_value('nan'))
        self.assertIsNone(_float_value('-1', nonnegative=True))
        self.assertAlmostEqual(linear_peak_db(1), 0)
        self.assertEqual(linear_peak_db(0), float('-inf'))

    def test_formats_normalize_correctly(self):
        self.assertEqual(_fields({'REPLAYGAIN_TRACK_GAIN': ['+1.20 dB']})['replaygain_track_gain'], ['+1.20 dB'])
        self.assertEqual(_fields({'TXXX:REPLAYGAIN_TRACK_GAIN': TXXX('-3.30 dB')})['replaygain_track_gain'], ['-3.30 dB'])
        self.assertEqual(_fields({'----:com.apple.iTunes:replaygain_album_peak': [b'1.005']})['replaygain_album_peak'], [b'1.005'])
        self.assertEqual(_fields({'WM/ReplayGain_Album_Gain': ['-5 dB']})['replaygain_album_gain'], ['-5 dB'])

    def test_flac_vorbis_comments_and_absent_lufs(self):
        audio = MockAudio({
            'replaygain_track_gain': ['-4.70 dB'], 'replaygain_track_peak': ['0.99'],
            'REPLAYGAIN_ALBUM_GAIN': ['-5.12 dB'], 'REPLAYGAIN_ALBUM_PEAK': ['1.01'],
        })
        with patch('mutagen.File', return_value=audio):
            read = read_existing_gain(Path('/tmp/test.flac'))
        self.assertEqual(read.error, '')
        self.assertTrue(read.info.tagged)
        self.assertEqual(read.info.track_gain, -4.7)
        self.assertEqual(read.info.album_gain, -5.12)
        self.assertEqual(read.info.album_peak, 1.01)
        self.assertNotIn('loudness', read.info.__dict__)

    def test_mp3_id3_and_mp4_freeform(self):
        for name, tag in [
            ('track.mp3', {'TXXX:replaygain_track_gain': TXXX('+2.10 dB')}),
            ('track.m4a', {'----:com.apple.iTunes:replaygain_track_gain': [b'+2.10 dB']}),
        ]:
            with self.subTest(name=name), patch('mutagen.File', return_value=MockAudio(tag)):
                self.assertEqual(read_existing_gain(Path(name)).info.track_gain, 2.1)

    def test_r128_is_separate_from_replaygain(self):
        with patch('mutagen.File', return_value=MockAudio({'R128_TRACK_GAIN': ['-256'], 'R128_ALBUM_GAIN': ['512']})):
            info = read_existing_gain(Path('example.opus')).info
        self.assertTrue(info.tagged)
        self.assertIsNone(info.track_gain)
        self.assertEqual(info.r128_track_gain, -1.0)
        self.assertEqual(info.r128_album_gain, 2.0)
        self.assertIsNone(_int_r128('2.50'))

    def test_untagged_and_unreadable_are_distinct(self):
        with patch('mutagen.File', return_value=MockAudio({})):
            result = read_existing_gain(Path('sample.flac'))
        self.assertFalse(result.info.tagged)
        self.assertFalse(result.error)
        with patch('mutagen.File', return_value=None):
            result = read_existing_gain(Path('unknown.tak'))
        self.assertFalse(result.info.tagged)
        self.assertTrue(result.error)

    def test_album_consistency(self):
        self.assertEqual(common_album_value([-4.7, -4.7, None]), (-4.7, False))
        self.assertEqual(common_album_value([-4.7, -5.7]), (None, True))
        self.assertEqual(common_album_value([None, None]), (None, False))

    def test_real_id3_tag_file_does_not_write(self):
        from mutagen.id3 import ID3, TXXX
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.mp3'
            tags = ID3()
            tags.add(TXXX(encoding=3, desc='REPLAYGAIN_TRACK_GAIN', text=['-2.00 dB']))
            tags.save(path)
            before = path.read_bytes()
            data = load_existing_tags([path])[path]
            self.assertEqual(data.info.track_gain, -2.0)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

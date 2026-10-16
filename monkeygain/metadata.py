"""Read existing ReplayGain metadata without changing an audio file.

Uses Mutagen's native tag readers. Stored ReplayGain peaks are linear
amplitudes; existing tags do not disclose whether the peak was oversampled.
Opus R128 gains are kept separate from conventional ReplayGain values.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class ExistingGain:
    track_gain: float | None = None
    track_peak: float | None = None
    album_gain: float | None = None
    album_peak: float | None = None
    r128_track_gain: float | None = None
    r128_album_gain: float | None = None

    @property
    def tagged(self) -> bool:
        return any(getattr(self, key) is not None for key in (
            'track_gain', 'track_peak', 'album_gain', 'album_peak',
            'r128_track_gain', 'r128_album_gain',
        ))


@dataclass(frozen=True)
class TagRead:
    info: ExistingGain = ExistingGain()
    error: str = ''


_GAIN_RE = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:dB)?\s*$', re.I)


def _float_value(value: object, *, nonnegative: bool = False) -> float | None:
    """Parse numeric ReplayGain fields, ignoring malformed/nonfinite tags."""
    if hasattr(value, 'value'):
        value = value.value
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'replace').strip('\x00')
    match = _GAIN_RE.fullmatch(str(value).strip())
    if not match:
        return None
    number = float(match.group(1))
    if not math.isfinite(number) or (nonnegative and number < 0):
        return None
    return number


def _int_r128(value: object) -> float | None:
    """R128_*_GAIN stores signed Q7.8 dB at the Opus -23 LUFS reference."""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, bytes):
        value = value.decode('utf-8', 'replace').strip('\x00')
    if not isinstance(value, (str, int)) or not re.fullmatch(r'[+-]?\d+', str(value).strip()):
        return None
    raw = int(value)
    return raw / 256 if -32768 <= raw <= 32767 else None


def _fields(tags: object) -> dict[str, object]:
    """Normalize Vorbis, APEv2, ID3 TXXX and MP4 freeform naming."""
    normalized: dict[str, object] = {}
    for key, value in tags.items():
        name = str(key)
        if name.casefold().startswith('txxx:'):
            name = name[5:]
            if hasattr(value, 'text'):
                value = value.text
        elif name.casefold().startswith('----:com.apple.itunes:'):
            name = name.split(':', 2)[-1]
        elif name.casefold().startswith('wm/'):
            name = name[3:]
        canonical = re.sub(r'[\s/-]+', '_', name).casefold()
        # Prefer first matching field, avoiding duplicate conflicting ID3 frames.
        normalized.setdefault(canonical, value)
    return normalized


def read_existing_gain(path: Path) -> TagRead:
    """Read supported tags; never writes tags, scans audio, or changes mtime.

    `error` means metadata could not be determined, NOT that there are no tags.
    An empty, error-free ExistingGain means the format was read successfully
    but no recognized ReplayGain fields were present.
    """
    try:
        from mutagen import File as audio_file
        from mutagen.id3 import ID3, ID3NoHeaderError
    except ImportError:
        return TagRead(error='Python Mutagen is missing (install python3-mutagen).')

    try:
        try:
            audio = audio_file(str(path), easy=False)
        except Exception:
            # Mutagen's MP3 parser can reject files that contain only a
            # valid ID3 header but no decodable MPEG frames. Read ID3 below.
            if path.suffix.lower() not in {'.mp3', '.mp2'}:
                raise
            audio = None
        if audio is None:
            # A tag-only MP3 or AAC may have no decodable audio frame, but
            # an ID3v2 header can still contain perfectly valid ReplayGain tags.
            if path.suffix.lower() in {'.mp3', '.mp2'}:
                try:
                    tags = ID3(str(path))
                except ID3NoHeaderError:
                    return TagRead(error='Audio metadata could not be decoded.')
            else:
                return TagRead(error='Audio metadata format is not supported by Mutagen.')
        else:
            tags = audio.tags
            if tags is None:
                return TagRead()
        values = _fields(tags)
        return TagRead(ExistingGain(
            track_gain=_float_value(values.get('replaygain_track_gain')),
            track_peak=_float_value(values.get('replaygain_track_peak'), nonnegative=True),
            album_gain=_float_value(values.get('replaygain_album_gain')),
            album_peak=_float_value(values.get('replaygain_album_peak'), nonnegative=True),
            r128_track_gain=_int_r128(values.get('r128_track_gain')),
            r128_album_gain=_int_r128(values.get('r128_album_gain')),
        ))
    except Exception as exc:
        # Unsupported/invalid inputs should not crash an import or be labelled
        # "not tagged". Include the filename in the UI diagnostic log instead.
        return TagRead(error=f'{type(exc).__name__}: {exc}')


def load_existing_tags(paths: Iterable[Path]) -> dict[Path, TagRead]:
    return {path: read_existing_gain(path) for path in paths}


def linear_peak_db(peak: float) -> float:
    return 20 * math.log10(peak) if peak > 0 else float('-inf')


def common_album_value(values: Iterable[float | None]) -> tuple[float | None, bool]:
    """Return an album tag only when all present copies agree (within tag rounding).

    The boolean is True if the files disagree. A partial album is represented
    by a value but should be described as partial elsewhere.
    """
    available = [value for value in values if value is not None]
    if not available:
        return None, False
    if any(abs(value - available[0]) > 0.011 for value in available[1:]):
        return None, True
    return available[0], False

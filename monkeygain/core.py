"""Pure Python music discovery, scan configuration and safe rsgain invocation.

No GTK imports: this module can be tested without a graphical session.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import math
from pathlib import Path
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
from typing import Callable, Iterable

# Precisely the formats documented for rsgain v3.4. Later rsgain versions
# add more; they should be enabled only after checking local backend support.
SUPPORTED_SUFFIXES = frozenset({
    '.aif', '.aiff', '.ape', '.flac', '.mp2', '.mp3', '.mp4', '.m4a', '.mpc',
    '.ogg', '.oga', '.spx', '.opus', '.snd', '.tak', '.wav', '.wv', '.wma',
})


def is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES and path.is_file()


def discover_audio(paths: Iterable[str | Path]) -> list[Path]:
    """Return sorted unique audio files; directory traversal never follows symlink dirs."""
    found: set[Path] = set()
    for raw in paths:
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            if is_audio_file(candidate):
                found.add(candidate.resolve())
            continue
        if not candidate.is_dir():
            continue
        for base, dirs, files in os.walk(candidate, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(base) / d).is_symlink())
            for name in files:
                item = Path(base) / name
                if is_audio_file(item):
                    found.add(item.resolve())
    return sorted(found, key=lambda p: (str(p.parent).casefold(), p.name.casefold()))


@dataclass(frozen=True)
class AlbumJob:
    folder: Path
    files: tuple[Path, ...]

    @property
    def label(self) -> str:
        return self.folder.name or str(self.folder)



def make_album_jobs(files: Iterable[Path]) -> list[AlbumJob]:
    """Treat each physical parent directory as an album (not metadata grouping)."""
    grouped: dict[Path, set[Path]] = {}
    for file in files:
        p = Path(file).resolve()
        if not is_audio_file(p):
            continue
        grouped.setdefault(p.parent, set()).add(p)
    return [
        AlbumJob(folder, tuple(sorted(items, key=lambda p: p.name.casefold())))
        for folder, items in sorted(grouped.items(), key=lambda x: str(x[0]).casefold())
    ]


@dataclass(frozen=True)
class ScanSettings:
    album: bool = True
    true_peak: bool = True
    loudness: int = -18
    clip_mode: str = 'p'
    max_peak: float = -1.0
    write_tags: bool = True
    skip_existing: bool = False

    def validate(self) -> None:
        if not -30 <= self.loudness <= -5:
            raise ValueError('Target loudness must be between -30 and -5 LUFS.')
        if self.clip_mode not in ('p', 'a', 'n'):
            raise ValueError('Invalid clipping protection mode.')
        if not -20 <= self.max_peak <= 0:
            raise ValueError('Maximum peak must be between -20 and 0 dB.')


def build_command(settings: ScanSettings, job: AlbumJob, binary: str = 'rsgain') -> list[str]:
    """Build argv without shell expansion or interpolation."""
    settings.validate()
    if not job.files:
        raise ValueError('This album contains no audio files.')
    argv = [binary, 'custom']
    if settings.album:
        argv.append('--album')
    if settings.true_peak:
        argv.append('--true-peak')
    argv += [
        f'--loudness={settings.loudness}',
        f'--clip-mode={settings.clip_mode}',
        f'--max-peak={settings.max_peak:g}',
        '--tagmode=i' if settings.write_tags else '--tagmode=s',
        '--output',  # Structured tab-separated results on stdout (rsgain 3.4).
    ]
    if settings.skip_existing:
        argv.append('--skip-existing')
    argv.extend(str(file) for file in job.files)
    return argv


def display_command(argv: list[str]) -> str:
    return shlex.join(argv)


@dataclass(frozen=True)
class BackendStatus:
    """Detected executable, version, and user-readable diagnostic on failure."""
    path: str | None = None
    version: str | None = None
    error: str = ''


def probe_backend(preferred_path: str = '') -> BackendStatus:
    """Find a working rsgain binary without relying exclusively on PATH.

    If a manual path was given, check only that path rather than quietly
    falling back to another installation. This keeps UI and scan in sync.
    """
    locations: list[str] = []
    if preferred_path.strip():
        name = os.path.expandvars(os.path.expanduser(preferred_path.strip()))
        if '/' not in name:
            resolved = shutil.which(name)
            locations.append(resolved or name)
        else:
            locations.append(name)
    else:
        located = shutil.which('rsgain')
        if located:
            locations.append(located)
        locations += [
            '/usr/bin/rsgain', '/usr/local/bin/rsgain',
            str(Path.home() / '.local' / 'bin' / 'rsgain'),
            '/snap/bin/rsgain',
        ]

    errors = []
    for name in dict.fromkeys(locations):
        path = Path(name)
        if not path.is_file():
            errors.append(f'{name}: file not found')
            continue
        if not os.access(path, os.X_OK):
            errors.append(f'{name}: not executable')
            continue
        try:
            response = subprocess.run(
                [str(path), '--version'], capture_output=True,
                text=True, errors='replace', check=False, timeout=6,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f'{name}: {exc}')
            continue
        if response.returncode != 0:
            detail = (response.stderr or response.stdout).strip()
            errors.append(f'{name}: exit {response.returncode}: {detail[:300]}')
            continue
        text = re.sub(r'\x1b\[[0-9;]*m', '', response.stdout + '\n' + response.stderr)
        match = re.search(r'\brsgain\s+v?(\d+(?:\.\d+){1,2})\b', text, re.I)
        # A successful --version confirms a functional binary, even if a
        # custom build presents its version differently.
        return BackendStatus(str(path.resolve()), match.group(1) if match else 'unknown')

    errors_text = '\n'.join(errors) if errors else 'No executable candidates were available.'
    return BackendStatus(error=(
        f'Unable to locate or launch rsgain.\n'
        f'Checked:\n{errors_text}\n'
        f'PATH={os.environ.get("PATH", "")}'
    ))


def backend_version(binary: str = 'rsgain') -> str | None:
    """Legacy convenience function for projects using MonkeyGain core."""
    return probe_backend('' if binary == 'rsgain' else binary).version



@dataclass(frozen=True)
class ScanMetric:
    """A single row from rsgain 3.4's --output tab-delimited report."""
    filename: str  # "Album" for album-wide measurements.
    loudness: float
    gain: float
    peak: float
    peak_db: float
    peak_type: str
    clipping_adjusted: bool

    @property
    def is_album(self) -> bool:
        return self.filename == 'Album'


def parse_metric(line: str, job: AlbumJob) -> ScanMetric | None:
    """Read an actual rsgain TSV data row, ignoring progress and log lines.

    Only accept track names belonging to the current job. This prevents
    arbitrary log output from being mistaken for scan measurements.
    """
    if '\t' not in line:
        return None
    try:
        cells = next(csv.reader([line.rstrip('\r\n')], delimiter='\t'))
    except csv.Error:
        return None
    if len(cells) != 7:
        return None
    name, loudness, gain, peak, peak_db, peak_type, clipped = cells
    if name != 'Album' and name not in {p.name for p in job.files}:
        return None
    if peak_type not in ('True', 'Sample') or clipped not in ('Y', 'N'):
        return None
    try:
        values = tuple(float(v.replace('−', '-').replace('∞', 'inf'))
                       for v in (loudness, gain, peak, peak_db))
    except ValueError:
        return None
    if any(math.isnan(v) for v in values):
        return None
    if peak != '0' and values[2] < 0:
        return None
    return ScanMetric(name, *values, peak_type, clipped == 'Y')


def current_track_from_log(line: str, job: AlbumJob) -> str | None:
    """Best-effort progress indication from rsgain's human-readable log."""
    match = re.search(r"Scanning '(.+?)'", re.sub(r'\x1b\[[0-9;]*m', '', line))
    if match:
        path = match.group(1)
        for item in job.files:
            if path == str(item):
                return item.name
    return None

class ScanRunner:
    """Single-worker subprocess queue; callbacks are invoked on worker threads."""
    def __init__(self, on_log: Callable[[str], None],
                 on_job: Callable[[int, str], None],
                 on_finish: Callable[[int, int, bool], None],
                 on_metric: Callable[[int, ScanMetric], None] | None = None,
                 on_track: Callable[[int, str], None] | None = None):
        self.on_log = on_log
        self.on_job = on_job
        self.on_finish = on_finish
        self.on_metric = on_metric or (lambda _idx, _metric: None)
        self.on_track = on_track or (lambda _idx, _track: None)
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, jobs: list[AlbumJob], settings: ScanSettings, binary: str = 'rsgain') -> None:
        if self.running:
            raise RuntimeError('A scan is already running.')
        if not jobs:
            raise ValueError('There are no albums to scan.')
        settings.validate()
        self._cancel.clear()
        self._thread = threading.Thread(target=self._work, args=(jobs, settings, binary), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _work(self, jobs: list[AlbumJob], settings: ScanSettings, binary: str) -> None:
        success = 0
        failed = 0
        for index, job in enumerate(jobs):
            if self._cancel.is_set():
                break
            self.on_job(index, 'running')
            argv = build_command(settings, job, binary)
            self.on_log(f'\n━━━ {index + 1}/{len(jobs)} · {job.label} ━━━\n')
            self.on_log(f'$ {display_command(argv)}\n')
            try:
                proc = subprocess.Popen(
                    argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, errors='replace', bufsize=1, start_new_session=True,
                )
                with self._lock:
                    self._process = proc
                # If cancellation happened in the tiny gap before storing proc.
                if self._cancel.is_set():
                    self.cancel()
                assert proc.stdout is not None
                with proc.stdout:
                    for line in proc.stdout:
                        self.on_log(line)
                        metric = parse_metric(line, job)
                        if metric is not None:
                            self.on_metric(index, metric)
                        track = current_track_from_log(line, job)
                        if track is not None:
                            self.on_track(index, track)
                rc = proc.wait()
                with self._lock:
                    self._process = None
                if self._cancel.is_set():
                    self.on_job(index, 'cancelled')
                    break
                if rc == 0:
                    success += 1
                    self.on_job(index, 'success')
                else:
                    failed += 1
                    self.on_job(index, 'failed')
                    self.on_log(f'rsgain exited with code {rc}.\n')
            except OSError as exc:
                failed += 1
                self.on_log(f'Failed to launch rsgain: {exc}\n')
                self.on_job(index, 'failed')
            finally:
                with self._lock:
                    self._process = None
        self.on_finish(success, failed, self._cancel.is_set())

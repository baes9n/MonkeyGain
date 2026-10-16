"""Pure Python music discovery, scan configuration and safe rsgain invocation.

No GTK imports: this module can be tested without a graphical session.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    '.aiff', '.ape', '.flac', '.mp2', '.mp3', '.m4a', '.mpc',
    '.ogg', '.oga', '.spx', '.opus', '.tak', '.wav', '.wv', '.wma',
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
            raise ValueError('El objetivo debe estar entre -30 y -5 LUFS.')
        if self.clip_mode not in ('p', 'a', 'n'):
            raise ValueError('Modo de protección inválido.')
        if not -20 <= self.max_peak <= 0:
            raise ValueError('El pico máximo debe estar entre -20 y 0 dB.')


def build_command(settings: ScanSettings, job: AlbumJob, binary: str = 'rsgain') -> list[str]:
    """Build argv without shell expansion or interpolation."""
    settings.validate()
    if not job.files:
        raise ValueError('No hay archivos en este álbum.')
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
    ]
    if settings.skip_existing:
        argv.append('--skip-existing')
    argv.extend(str(file) for file in job.files)
    return argv


def display_command(argv: list[str]) -> str:
    return shlex.join(argv)


def backend_version(binary: str = 'rsgain') -> str | None:
    exe = shutil.which(binary)
    if not exe:
        return None
    try:
        response = subprocess.run([exe, '--version'], capture_output=True, text=True,
                                  check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r'\brsgain\s+(\d+\.\d+(?:\.\d+)?)', response.stdout + response.stderr)
    return match.group(1) if match else None


class ScanRunner:
    """Single-worker subprocess queue; callbacks are invoked on worker threads."""
    def __init__(self, on_log: Callable[[str], None],
                 on_job: Callable[[int, str], None],
                 on_finish: Callable[[int, int, bool], None]):
        self.on_log = on_log
        self.on_job = on_job
        self.on_finish = on_finish
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, jobs: list[AlbumJob], settings: ScanSettings) -> None:
        if self.running:
            raise RuntimeError('Ya hay un análisis en ejecución.')
        if not jobs:
            raise ValueError('No hay álbumes para procesar.')
        settings.validate()
        self._cancel.clear()
        self._thread = threading.Thread(target=self._work, args=(jobs, settings), daemon=True)
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

    def _work(self, jobs: list[AlbumJob], settings: ScanSettings) -> None:
        success = 0
        failed = 0
        for index, job in enumerate(jobs):
            if self._cancel.is_set():
                break
            self.on_job(index, 'running')
            argv = build_command(settings, job)
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
                for line in proc.stdout:
                    self.on_log(line)
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
                    self.on_log(f'Error: rsgain terminó con código {rc}.\n')
            except OSError as exc:
                failed += 1
                self.on_log(f'Error ejecutando rsgain: {exc}\n')
                self.on_job(index, 'failed')
            finally:
                with self._lock:
                    self._process = None
        self.on_finish(success, failed, self._cancel.is_set())

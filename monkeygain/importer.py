"""Cancellable, incremental music import. No GTK code runs on worker threads."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import threading
import time
from typing import Callable, Iterable, Iterator

from .core import SUPPORTED_SUFFIXES, AlbumJob
from .metadata import TagRead, load_existing_tags

BATCH_SIZE = 64


@dataclass(frozen=True)
class ImportUpdate:
    phase: str  # discovering, reading, complete, cancelled, error
    discovered: int
    inspected: int
    files: tuple[Path, ...] = ()
    readings: dict[Path, TagRead] | None = None
    message: str = ''


def iter_audio_files(paths: Iterable[str | Path], cancel: threading.Event) -> Iterator[Path]:
    """Yield distinct local supported files, without following directory links.

    A directory can be large, so we yield rather than constructing every
    Path and running metadata inspection on the GTK main thread.
    """
    seen: set[Path] = set()
    for raw in paths:
        if cancel.is_set():
            return
        root = Path(raw).expanduser()
        if root.is_file():
            if root.suffix.lower() in SUPPORTED_SUFFIXES:
                try:
                    resolved = root.resolve()
                except OSError:
                    continue
                if resolved not in seen:
                    seen.add(resolved)
                    yield resolved
        elif root.is_dir():
            for base, dirs, names in os.walk(root, followlinks=False):
                if cancel.is_set():
                    return
                dirs[:] = sorted(d for d in dirs if not (Path(base) / d).is_symlink())
                for name in names:
                    if cancel.is_set():
                        return
                    if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
                        continue
                    p = Path(base) / name
                    try:
                        if not p.is_file():
                            continue
                        resolved = p.resolve()
                    except OSError:
                        continue
                    if resolved not in seen:
                        seen.add(resolved)
                        yield resolved


class ImportRunner:
    """Imports supported files in batches. Callback runs on worker thread.

    Progress during discovery is indeterminate; after discovery finishes the
    completed/total files ratio reflects genuine metadata-reading progress.
    """
    def __init__(self, on_update: Callable[[ImportUpdate], None], *, batch_size: int = BATCH_SIZE):
        self.on_update = on_update
        self.batch_size = max(1, batch_size)
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, paths: Iterable[str | Path]) -> None:
        if self.running:
            raise RuntimeError('An import is already running.')
        self._cancel.clear()
        self._thread = threading.Thread(target=self._work, args=(tuple(paths),), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _work(self, paths: tuple[str | Path, ...]) -> None:
        discovered: list[Path] = []
        inspected = 0
        try:
            self.on_update(ImportUpdate('discovering', 0, 0))
            last_update = time.monotonic()
            for path in iter_audio_files(paths, self._cancel):
                discovered.append(path)
                now = time.monotonic()
                if now - last_update >= 0.20:
                    self.on_update(ImportUpdate('discovering', len(discovered), 0))
                    last_update = now
            if self._cancel.is_set():
                self.on_update(ImportUpdate('cancelled', len(discovered), inspected))
                return
            discovered.sort(key=lambda p: (str(p.parent).casefold(), p.name.casefold()))
            total = len(discovered)
            self.on_update(ImportUpdate('reading', total, 0))
            for offset in range(0, total, self.batch_size):
                if self._cancel.is_set():
                    self.on_update(ImportUpdate('cancelled', total, inspected))
                    return
                batch = tuple(discovered[offset:offset + self.batch_size])
                # Safely recover from a damaged file inside a batch rather
                # than losing metadata for all other imported tracks.
                try:
                    readings = load_existing_tags(batch)
                except Exception as exc:
                    readings = {p: TagRead(error=str(exc)) for p in batch}
                inspected += len(batch)
                self.on_update(ImportUpdate('reading', total, inspected, batch, readings))
            self.on_update(ImportUpdate('complete', total, inspected))
        except Exception as exc:
            self.on_update(ImportUpdate('error', len(discovered), inspected, message=str(exc)))


PAGE_SIZE = 40
TRACKS_PER_BATCH = 60


def page_bounds(total: int, page: int, size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """Clamp page and return (page index, start, end) for bounded GTK rows."""
    if size <= 0:
        raise ValueError('Page size must be positive')
    count = max(1, (max(0, total) + size - 1) // size)
    page = max(0, min(page, count - 1))
    start = page * size
    return page, start, min(start + size, max(0, total))


def matches_tag_filter(readings: Iterable[TagRead | None], selected: int) -> bool:
    """Filter album view by existing tag coverage; never changes scan queue.

    0=all, 1=all tagged, 2=missing at least one tag, 3=read errors.
    """
    if selected == 0:
        return True
    data = tuple(readings)
    if selected == 1:
        return bool(data) and all(r is not None and r.info.tagged for r in data)
    if selected == 2:
        return any(r is None or (not r.error and not r.info.tagged) for r in data)
    if selected == 3:
        return any(r is not None and bool(r.error) for r in data)
    return True


def group_imported_paths(files: Iterable[Path]) -> list[AlbumJob]:
    """Build album jobs from already-validated canonical paths, with no disk I/O.

    The streaming importer has already checked/normalized every path in its
    worker. GTK must not repeat stat()/resolve() thousands of times on HDDs.
    """
    folders: dict[Path, list[Path]] = {}
    for file in files:
        folders.setdefault(file.parent, []).append(file)
    return [AlbumJob(folder, tuple(sorted(filenames, key=lambda p: p.name.casefold())))
            for folder, filenames in sorted(folders.items(),
                                            key=lambda pair: str(pair[0]).casefold())]


def matches_album(query: str, album_name: str, artist_folder: str,
                  track_names: Iterable[str]) -> bool:
    """Case-insensitive multi-term search over album, artist and track names."""
    terms = query.casefold().split()
    if not terms:
        return True
    haystack = ' '.join((album_name, artist_folder, *track_names)).casefold()
    return all(term in haystack for term in terms)

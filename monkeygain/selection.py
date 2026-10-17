"""Album selection and scan planning without GTK or filesystem I/O."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, TypeVar

T = TypeVar('T')


class AlbumSelection:
    """Selection keyed by album folder, independent of filters and page rows."""

    def __init__(self) -> None:
        self.selected: set[Path] = set()

    def toggle(self, folder: Path, checked: bool) -> None:
        if checked:
            self.selected.add(folder)
        else:
            self.selected.discard(folder)

    def select(self, folders: Iterable[Path]) -> None:
        self.selected.update(folders)

    def clear(self) -> None:
        self.selected.clear()

    def prune(self, folders: Iterable[Path]) -> None:
        self.selected.intersection_update(folders)

    def count(self) -> int:
        return len(self.selected)


def plan_scan(jobs: Iterable[T], selected: set[Path], *, all_albums: bool) -> list[T]:
    """Build a stable scan snapshot in collection order (not displayed order).

    AlbumJob-like inputs expose `.folder`. Filtering never changes the scan
    snapshot; only an explicit user selection does for selected-only scans.
    """
    if all_albums:
        return list(jobs)
    return [job for job in jobs if job.folder in selected]


def plan_result_reveal(
    scanned_folders: Iterable[Path],
    visible_folders: set[Path],
    measured_folders: set[Path],
    expanded_folders: set[Path],
    *,
    limit: int = 2,
) -> list[Path]:
    """Choose just-completed, on-page albums whose results can be opened.

    Keep the GTK row count bounded for big scans, respect user-opened albums,
    and never auto-open unscanned or filtered-out folders.
    """
    if limit <= 0:
        return []
    eligible = [folder for folder in scanned_folders
                if folder in visible_folders and folder in measured_folders]
    remaining = max(0, limit - sum(folder in expanded_folders for folder in eligible))
    return [folder for folder in eligible if folder not in expanded_folders][:remaining]

"""Plain-Python journal for live, human-readable scanner activity.

The detailed rsgain output is preserved separately from the activity feed.
Recording an activity event never implies that a track measurement exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def format_elapsed(seconds: int | float) -> str:
    """Return a stable mm:ss / hh:mm:ss elapsed duration."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{seconds:02d}'
    return f'{minutes}:{seconds:02d}'


LEVEL_ICONS = {
    'info': '•',
    'working': '◌',
    'success': '✓',
    'warning': '!',
    'error': '✕',
}


@dataclass(frozen=True)
class ActivityEvent:
    level: str
    message: str
    elapsed: int | None = None

    def display(self) -> str:
        clock = f'[{format_elapsed(self.elapsed)}]' if self.elapsed is not None else '       '
        return f'{clock}  {LEVEL_ICONS.get(self.level, "•")}  {self.message}\n'


@dataclass
class ActivityJournal:
    events: list[ActivityEvent] = field(default_factory=list)
    raw_chunks: list[str] = field(default_factory=list)

    def clear(self) -> None:
        self.events.clear()
        self.raw_chunks.clear()

    def add(self, level: str, message: str, elapsed: int | None = None) -> ActivityEvent:
        event = ActivityEvent(level, message, elapsed)
        self.events.append(event)
        return event

    def add_raw(self, message: str) -> None:
        self.raw_chunks.append(message)

    def raw_text(self) -> str:
        return ''.join(self.raw_chunks)

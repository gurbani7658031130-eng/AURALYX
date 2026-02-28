"""
Auralyx Music — Utility Helpers
Formatting, time conversion, and miscellaneous helpers.
"""

import logging
import time

logger = logging.getLogger(__name__)


def format_duration(seconds: int) -> str:
    """
    Convert seconds to a human-readable duration string.

    Examples:
        format_duration(65)  -> "01:05"
        format_duration(3661) -> "1:01:01"
    """
    if seconds < 0:
        return "00:00"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def truncate(text: str, max_length: int = 40) -> str:
    """Truncate a string and add ellipsis if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def readable_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def escape_markdown(text: str) -> str:
    """Escape Markdown V2 special characters for Telegram."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


class Timer:
    """Simple async-compatible timer for measuring execution time."""

    def __init__(self):
        self._start: float = 0
        self._end: float = 0

    def start(self):
        self._start = time.perf_counter()

    def stop(self) -> float:
        self._end = time.perf_counter()
        return self.elapsed

    @property
    def elapsed(self) -> float:
        """Return elapsed time in seconds."""
        end = self._end if self._end else time.perf_counter()
        return round(end - self._start, 3)

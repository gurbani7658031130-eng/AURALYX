"""
Auralyx Music - Queue Manager
In-memory queue management for per-chat playback.
Uses collections.deque for O(1) popleft instead of O(n) list.pop(0).
"""

import logging
import random
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory queues: { chat_id: deque([track_dict, ...]) }
_queues: dict[int, deque] = {}


def get_queue(chat_id: int) -> list[dict]:
    """Get the current queue for a chat. Returns a list copy."""
    q = _queues.get(chat_id)
    return list(q) if q else []


def add_to_queue(chat_id: int, track: dict, force: bool = False) -> int:
    """
    Add a track to the chat queue.

    Returns 0-based queue position.
    """
    if chat_id not in _queues or force:
        _queues[chat_id] = deque()

    _queues[chat_id].append(track)
    position = len(_queues[chat_id]) - 1

    action = "Forced" if force else "Added"
    logger.info("%s '%s' to queue for chat %s (position %s)", action, track.get("title"), chat_id, position)
    return position


def append_track(chat_id: int, track: dict) -> int:
    """Append a track and return its position."""
    if chat_id not in _queues:
        _queues[chat_id] = deque()
    _queues[chat_id].append(track)
    return len(_queues[chat_id]) - 1


def prepend_track(chat_id: int, track: dict) -> int:
    """Prepend a track and return position 0."""
    if chat_id not in _queues:
        _queues[chat_id] = deque()
    _queues[chat_id].appendleft(track)
    return 0


def pop_from_queue(chat_id: int) -> Optional[dict]:
    """Remove and return the first track from queue."""
    queue = _queues.get(chat_id)
    if not queue:
        return None
    track = queue.popleft()
    logger.info("Popped '%s' from queue for chat %s", track.get("title"), chat_id)
    if not queue:
        del _queues[chat_id]
    return track


def clear_queue(chat_id: int):
    """Clear the entire queue for a chat."""
    if chat_id in _queues:
        del _queues[chat_id]
        logger.info("Queue cleared for chat %s", chat_id)


def current_track(chat_id: int) -> Optional[dict]:
    """Get currently playing track without removing it."""
    queue = _queues.get(chat_id)
    return queue[0] if queue else None


def queue_size(chat_id: int) -> int:
    """Return the queue size for chat."""
    q = _queues.get(chat_id)
    return len(q) if q else 0


def queue_length(chat_id: int) -> int:
    """Compatibility alias for queue size."""
    return queue_size(chat_id)


def has_duplicate(chat_id: int, url: str, title: str = "") -> bool:
    """Return True if exact URL or exact normalized title exists in queue."""
    q = _queues.get(chat_id)
    if not q:
        return False

    normalized_title = (title or "").strip().lower()
    for track in q:
        if url and track.get("url") == url:
            return True
        if normalized_title and track.get("title", "").strip().lower() == normalized_title:
            return True
    return False


def shuffle_queue(chat_id: int) -> int:
    """
    Shuffle queue while keeping currently playing item in place.
    Returns number of shuffled entries.
    """
    q = _queues.get(chat_id)
    if not q or len(q) < 3:
        return 0

    items = list(q)
    current = items[0]
    rest = items[1:]
    random.shuffle(rest)
    _queues[chat_id] = deque([current] + rest)
    return len(rest)


def remove_position(chat_id: int, position: int) -> Optional[dict]:
    """
    Remove a 1-based queue position and return removed track.
    Position 1 (current track) is not removable through this helper.
    """
    q = _queues.get(chat_id)
    if not q:
        return None
    if position <= 1 or position > len(q):
        return None

    items = list(q)
    removed = items.pop(position - 1)
    _queues[chat_id] = deque(items)
    return removed


def is_queue_empty(chat_id: int) -> bool:
    """Check if queue is empty."""
    return chat_id not in _queues or len(_queues[chat_id]) == 0


def active_queue_count() -> int:
    """Return number of chats with active queues."""
    return len(_queues)


# Alias for convenience
pop_queue = pop_from_queue

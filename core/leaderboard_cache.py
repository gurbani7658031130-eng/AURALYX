"""
Auralyx Music — Leaderboard Cache
In-memory TTL cache for /toprich and /topkills to reduce DB load.
Thread-safe, async-safe, with invalidation hooks.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Cache storage
_cache: dict[str, dict] = {}
# { "wallet": {"data": [...], "expires": timestamp}, "kills": {...} }

_lock = asyncio.Lock()

CACHE_TTL = 60  # seconds


async def get_cached(field: str, limit: int = 10) -> Optional[list[dict]]:
    """Get cached leaderboard data if still fresh."""
    async with _lock:
        entry = _cache.get(field)
        if entry and time.time() < entry["expires"]:
            return entry["data"][:limit]
    return None


async def set_cached(field: str, data: list[dict]):
    """Store leaderboard data in cache."""
    async with _lock:
        _cache[field] = {
            "data": data,
            "expires": time.time() + CACHE_TTL,
        }


async def invalidate(field: Optional[str] = None):
    """
    Invalidate cache for a specific field, or all if None.
    Called automatically when balance/kills change.
    """
    async with _lock:
        if field:
            _cache.pop(field, None)
        else:
            _cache.clear()


async def invalidate_wallet():
    """Shortcut: invalidate wallet leaderboard."""
    await invalidate("wallet")


async def invalidate_kills():
    """Shortcut: invalidate kills leaderboard."""
    await invalidate("kills")

"""Music settings cache helpers."""

import time
from database.mongo import get_music_settings, set_music_setting, update_music_settings

_CACHE_TTL = 30.0
_cache: dict[int, tuple[dict, float]] = {}


async def fetch_settings(chat_id: int) -> dict:
    now = time.monotonic()
    cached = _cache.get(chat_id)
    if cached and now < cached[1]:
        return dict(cached[0])

    data = await get_music_settings(chat_id)
    _cache[chat_id] = (dict(data), now + _CACHE_TTL)
    return dict(data)


async def set_setting(chat_id: int, key: str, value):
    await set_music_setting(chat_id, key, value)
    cur = await fetch_settings(chat_id)
    cur[key] = value
    _cache[chat_id] = (cur, time.monotonic() + _CACHE_TTL)


async def set_settings(chat_id: int, updates: dict):
    await update_music_settings(chat_id, updates)
    cur = await fetch_settings(chat_id)
    cur.update(updates)
    _cache[chat_id] = (cur, time.monotonic() + _CACHE_TTL)


def invalidate(chat_id: int):
    _cache.pop(chat_id, None)

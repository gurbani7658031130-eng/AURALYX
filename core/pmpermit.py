"""Global private-message permit flag with TTL cache."""

import time
from database.mongo import get_dynamic_config, set_dynamic_config

_KEY = "pm_permit"
_CACHE_TTL = 20.0
_cached: tuple[bool, float] | None = None


async def is_pm_permitted() -> bool:
    """Whether non-sudo/non-owner users can use bot in PM."""
    global _cached
    now = time.monotonic()
    if _cached and now < _cached[1]:
        return bool(_cached[0])

    val = await get_dynamic_config(_KEY, default=True)
    allowed = bool(val)
    _cached = (allowed, now + _CACHE_TTL)
    return allowed


async def set_pm_permit(state: bool):
    """Persist PM permit flag and refresh cache."""
    global _cached
    await set_dynamic_config(_KEY, bool(state))
    _cached = (bool(state), time.monotonic() + _CACHE_TTL)

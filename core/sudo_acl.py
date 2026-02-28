"""Owner/sudo and approval-permission ACL helpers."""

import time

from config import OWNER_ID, SUDO_USERS
from database.approval_sqlite import (
    approve_user as sqlite_approve_user,
    disapprove_user as sqlite_disapprove_user,
    get_user_permissions as sqlite_get_user_permissions,
    init_db as sqlite_init_db,
    list_approved_users as sqlite_list_approved_users,
    set_user_permissions as sqlite_set_user_permissions,
)

AVAILABLE_PERMISSIONS = [
    "ban",
    "mute",
    "unmute",
    "broadcast",
    "stats",
    "restart",
    "logs",
]

_CACHE_TTL = 20.0
_perm_cache: dict[int, tuple[set[str], float]] = {}


def _is_static_sudo(user_id: int) -> bool:
    if not user_id:
        return False
    if int(user_id) == int(OWNER_ID):
        return True
    return int(user_id) in {int(x) for x in (SUDO_USERS or set())}


async def is_sudo(user_id: int) -> bool:
    """True for owner and static env sudo users."""
    return _is_static_sudo(int(user_id or 0))


async def list_approved_users(limit: int = 500) -> list[dict]:
    await sqlite_init_db()
    return await sqlite_list_approved_users(limit=limit)


async def approve_user(
    user_id: int,
    approved_by: int,
    permissions: list[str],
    reason: str = "",
    expiry_time: int | None = None,
) -> bool:
    """Create approved-user record; False if duplicate."""
    await sqlite_init_db()
    safe_permissions = [p for p in permissions if p in AVAILABLE_PERMISSIONS]
    ok = await sqlite_approve_user(
        int(user_id),
        approved_by=int(approved_by),
        permissions=safe_permissions,
        reason=reason,
        expiry_time=expiry_time,
    )
    await invalidate_permission_cache(int(user_id))
    return ok


async def disapprove_user(user_id: int) -> bool:
    await sqlite_init_db()
    ok = await sqlite_disapprove_user(int(user_id))
    await invalidate_permission_cache(int(user_id))
    return ok


async def set_permissions(user_id: int, permissions: list[str]) -> bool:
    """Replace permission set for an already-approved user."""
    await sqlite_init_db()
    safe_permissions = [p for p in permissions if p in AVAILABLE_PERMISSIONS]
    ok = await sqlite_set_user_permissions(int(user_id), safe_permissions)
    await invalidate_permission_cache(int(user_id))
    return ok


async def get_permissions(user_id: int) -> set[str]:
    """Get granted permission keys for approved users."""
    uid = int(user_id or 0)
    if uid == int(OWNER_ID):
        return set(AVAILABLE_PERMISSIONS)

    now = time.monotonic()
    cached = _perm_cache.get(uid)
    if cached and now < cached[1]:
        return set(cached[0])

    await sqlite_init_db()
    perms = set(await sqlite_get_user_permissions(uid))
    perms = {p for p in perms if p in AVAILABLE_PERMISSIONS}
    _perm_cache[uid] = (set(perms), now + _CACHE_TTL)
    return perms


async def has_permission(user_id: int, permission: str) -> bool:
    """Owner or static sudo bypasses; otherwise check approved permissions."""
    uid = int(user_id or 0)
    if _is_static_sudo(uid):
        return True
    if permission not in AVAILABLE_PERMISSIONS:
        return False
    perms = await get_permissions(uid)
    return permission in perms


async def is_approved_user(user_id: int) -> bool:
    """True when user has at least one approved permission."""
    uid = int(user_id or 0)
    if _is_static_sudo(uid):
        return True
    perms = await get_permissions(uid)
    return len(perms) > 0


async def invalidate_permission_cache(user_id: int | None = None):
    if user_id is None:
        _perm_cache.clear()
    else:
        _perm_cache.pop(int(user_id), None)


# Backward compatibility for existing imports in the codebase
async def list_sudo_users(limit: int = 500) -> list[dict]:
    return await list_approved_users(limit=limit)


async def unapprove_user(user_id: int) -> bool:
    return await disapprove_user(int(user_id))


async def invalidate_cache():
    await invalidate_permission_cache(None)

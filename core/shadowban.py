"""
Auralyx Music — Core: Shadowban
Silent user blocking system with in-memory check + DB persistence.
"""

import logging
from typing import Set
from database.mongo import stats_col

logger = logging.getLogger(__name__)

# In-memory shadowban list for O(1) checks
_shadowbanned_users: Set[int] = set()


async def load_state():
    """Load shadowbanned users from DB on startup."""
    global _shadowbanned_users
    doc = await stats_col.find_one({"key": "shadowbanned_users"})
    if doc and isinstance(doc.get("value"), list):
        _shadowbanned_users = set(doc["value"])
        if _shadowbanned_users:
            logger.info("Loaded %d shadowbanned users.", len(_shadowbanned_users))


async def shadow_ban(user_id: int):
    """Silently block a user from interacting."""
    global _shadowbanned_users
    _shadowbanned_users.add(user_id)
    await stats_col.update_one(
        {"key": "shadowbanned_users"},
        {"$set": {"value": list(_shadowbanned_users)}},
        upsert=True,
    )
    logger.warning("User %d has been SHADOWBANNED.", user_id)


async def shadow_unban(user_id: int):
    """Remove shadowban from a user."""
    global _shadowbanned_users
    _shadowbanned_users.discard(user_id)
    await stats_col.update_one(
        {"key": "shadowbanned_users"},
        {"$set": {"value": list(_shadowbanned_users)}},
        upsert=True,
    )
    logger.info("User %d has been unshadowbanned.", user_id)


def is_shadowbanned(user_id: int) -> bool:
    """Check if a user is shadowbanned (zero DB cost)."""
    return user_id in _shadowbanned_users

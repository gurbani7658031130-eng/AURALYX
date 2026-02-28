"""
Auralyx Music — Maintenance Mode
In-memory flag + DB persistence. Survives restarts.
"""

import logging
from database.mongo import stats_col

logger = logging.getLogger(__name__)

# In-memory flag (fast check, no DB hit per command)
_maintenance_on = False


async def load_state():
    """Load maintenance state from DB on startup."""
    global _maintenance_on
    doc = await stats_col.find_one({"key": "maintenance"})
    _maintenance_on = bool(doc and doc.get("value"))
    if _maintenance_on:
        logger.warning("⚠️ Bot is starting in MAINTENANCE MODE")


async def set_maintenance(on: bool):
    """Toggle maintenance mode (persisted to DB)."""
    global _maintenance_on
    _maintenance_on = on
    await stats_col.update_one(
        {"key": "maintenance"},
        {"$set": {"key": "maintenance", "value": on}},
        upsert=True,
    )
    logger.info("Maintenance mode %s", "ENABLED" if on else "DISABLED")


def is_maintenance() -> bool:
    """Check if maintenance mode is active (zero DB cost)."""
    return _maintenance_on

"""
Auralyx Music — MongoDB Layer
Async MongoDB with economy schema, auto-user creation, and atomic helpers.
"""

import logging
import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from config import MONGO_URI
from core.leaderboard_cache import invalidate_wallet, invalidate_kills

logger = logging.getLogger(__name__)

# ── Fast DB Memory Cache ──
class SimpleCache:
    """Memory dict with TTL eviction and bounded size to prevent RAM leaks."""
    __slots__ = ("_store", "ttl", "max_size")

    def __init__(self, ttl=60, max_size=5000):
        self._store: dict[str, tuple] = {}
        self.ttl = ttl
        self.max_size = max_size

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        val, expiry = entry
        if time.monotonic() < expiry:
            return val
        self._store.pop(key, None)
        return None

    def set(self, key: str, value):
        # Evict oldest entries when exceeding max size
        if len(self._store) >= self.max_size:
            now = time.monotonic()
            # Remove expired entries first
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
            # If still too large, clear half
            if len(self._store) >= self.max_size:
                keys = list(self._store.keys())
                for k in keys[: len(keys) // 2]:
                    del self._store[k]
        self._store[key] = (value, time.monotonic() + self.ttl)

    def delete(self, key: str):
        self._store.pop(key, None)

    def clear(self):
        self._store.clear()

    def __len__(self):
        return len(self._store)

_doc_cache = SimpleCache(ttl=60, max_size=5000)

_client = AsyncIOMotorClient(MONGO_URI)
db = _client.auralyx

# ── Collections ──────────────────────────────
groups_col = db["groups"]
users_col = db["users"]
economy_col = db["economy"]
stats_col = db["stats"]
gban_col = db["gbans"]
warnings_col = db["warnings"]
music_settings_col = db["music_settings"]
playlists_col = db["playlists"]
music_history_col = db["music_history"]
sudo_users_col = db["sudo_users"]
instance_lock_col = db["instance_lock"]

# ── Default economy document ─────────────────
_DEFAULT_ECONOMY = {
    "wallet": 0,
    "bank": 0,
    "kills": 0,
    "deaths": 0,
    "protection_until": 0,
    "last_daily": 0,
    "last_work": 0,
    "last_crime": 0,
    "last_beg": 0,
    "last_fish": 0,
    "last_hunt": 0,
    "vip_level": 0,
    "vip_expiry": 0,
    "custom_title": "",
    "streak": 0,
    "xp": 0,
    "level": 1,
    "inventory": [],
    "partner_id": 0,
    "afk": "",
    "afk_time": 0,
    "games_won": 0,
    "games_lost": 0,
}

_DEFAULT_MUSIC_SETTINGS = {
    "autoplay": False,
    "loop_mode": "off",  # off | track | queue
    "queue_cap": 50,
    "vote_skip_threshold": 3,
    "max_duration": 3600,
    "default_volume": 100,
}


async def ensure_indexes():
    """Create MongoDB indexes for efficient queries."""
    try:
        # Chat/User lookups
        await groups_col.create_index("chat_id", unique=True, background=True)
        await users_col.create_index("user_id", unique=True, background=True)
        await economy_col.create_index("user_id", unique=True, background=True)
        await stats_col.create_index("key", unique=True, background=True)
        
        # Leaderboard sorts (Economy)
        await economy_col.create_index([("wallet", -1)], background=True)
        await economy_col.create_index([("kills", -1)], background=True)
        
        # Filtering for tasks/status
        await economy_col.create_index("last_daily", background=True)
        await economy_col.create_index("vip_level", background=True)
        
        # Global bans
        await gban_col.create_index("user_id", unique=True, background=True)
        
        # Warnings
        await warnings_col.create_index([("chat_id", 1), ("user_id", 1)], background=True)
        
        # XP/Level leaderboard
        await economy_col.create_index([("xp", -1)], background=True)

        # Music settings / playlists / history
        await music_settings_col.create_index("chat_id", unique=True, background=True)
        await playlists_col.create_index([("chat_id", 1), ("name", 1)], unique=True, background=True)
        await music_history_col.create_index([("chat_id", 1), ("played_at", -1)], background=True)
        await music_history_col.create_index([("chat_id", 1), ("track_key", 1)], background=True)
        await sudo_users_col.create_index("user_id", unique=True, background=True)
        # Global singleton lock cleanup.
        await instance_lock_col.create_index("expires_at", expireAfterSeconds=0, background=True)
        
        logger.info("MongoDB indexes ensured (all collections).")
    except Exception as e:
        logger.error("Failed to create indexes: %s", e)


# ── User Helpers ─────────────────────────────
async def ensure_user(user_id: int, name: str = "Unknown") -> dict:
    """
    Get or create a user's economy document.
    Returns the full economy document. Results are cached.
    """
    cache_key = f"eco_{user_id}"
    cached = _doc_cache.get(cache_key)
    if cached is not None:
        return cached

    doc = await economy_col.find_one({"user_id": user_id})
    if doc:
        _doc_cache.set(cache_key, doc)
        return doc

    new_doc = {"user_id": user_id, "name": name, **_DEFAULT_ECONOMY}
    await economy_col.insert_one(new_doc)
    _doc_cache.set(cache_key, new_doc)
    logger.info("Auto-created economy doc for user %s", user_id)
    return new_doc


async def get_user_economy(user_id: int) -> dict:
    """Get a user's economy data, creating if missing. Uses cache."""
    return await ensure_user(user_id)


async def update_wallet(user_id: int, amount: int) -> None:
    """Atomically increment a user's wallet. Creates doc if missing."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$inc": {"wallet": amount}},
    )
    _doc_cache.delete(f"eco_{user_id}")
    await invalidate_wallet()


async def atomic_update_wallet(user_id: int, amount: int, min_balance: int = 0) -> bool:
    """
    Update wallet only if resulting balance >= min_balance.
    Prevents negative balance and race conditions.
    Returns: True if updated, False if insufficient funds.
    """
    await ensure_user(user_id)
    
    # filter for atomic check: wallet + amount >= min_balance
    # which is wallet >= min_balance - amount
    query = {
        "user_id": user_id,
        "wallet": {"$gte": min_balance - amount if amount < 0 else 0}
    }
    
    result = await economy_col.update_one(
        query,
        {"$inc": {"wallet": amount}}
    )
    
    if result.modified_count > 0:
        _doc_cache.delete(f"eco_{user_id}")
        await invalidate_wallet()
        return True
    return False


async def set_wallet(user_id: int, amount: int) -> None:
    """Set a user's wallet to an exact amount."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"wallet": max(0, amount)}},
    )
    _doc_cache.delete(f"eco_{user_id}")


async def update_bank(user_id: int, amount: int) -> None:
    """Atomically increment a user's bank."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$inc": {"bank": amount}},
    )
    _doc_cache.delete(f"eco_{user_id}")


async def update_kills(user_id: int, amount: int = 1) -> None:
    """Atomically increment kills."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$inc": {"kills": amount}},
    )
    await invalidate_kills()
    _doc_cache.delete(f"eco_{user_id}")


async def update_deaths(user_id: int, amount: int = 1) -> None:
    """Atomically increment deaths."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$inc": {"deaths": amount}},
    )
    _doc_cache.delete(f"eco_{user_id}")


async def set_protection(user_id: int, until: int) -> None:
    """Set protection timestamp."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"protection_until": until}},
    )
    _doc_cache.delete(f"eco_{user_id}")


async def is_protected(user_id: int) -> bool:
    """Check if a user is currently protected."""
    doc = await get_user_economy(user_id)
    return doc.get("protection_until", 0) > int(time.time())


async def set_last_daily(user_id: int, streak: int = 0) -> None:
    """Update last daily claim timestamp and streak."""
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"last_daily": int(time.time()), "streak": streak}},
    )
    _doc_cache.delete(f"eco_{user_id}")


async def set_vip(user_id: int, level: int, duration_days: int) -> None:
    """Set a user's VIP level and expiry."""
    expiry = int(time.time()) + (duration_days * 86400) if duration_days > 0 else 0
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"vip_level": level, "vip_expiry": expiry}},
        upsert=True
    )
    _doc_cache.delete(f"eco_{user_id}")


async def set_custom_title(user_id: int, title: str) -> None:
    """Set a user's custom glowing title."""
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"custom_title": title[:20]}},
        upsert=True
    )
    _doc_cache.delete(f"eco_{user_id}")


async def reset_user_economy(user_id: int) -> None:
    """Reset a user's economy to defaults."""
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": _DEFAULT_ECONOMY},
        upsert=True,
    )
    _doc_cache.delete(f"eco_{user_id}")


async def wipe_all_economy() -> int:
    """Delete ALL economy documents. Returns count deleted."""
    result = await economy_col.delete_many({})
    _doc_cache.clear()
    return result.deleted_count


async def get_top_users(field: str, limit: int = 10) -> list[dict]:
    """Get top users sorted by a field (wallet, kills, etc). strictly whitelisted."""
    if field not in ["wallet", "kills", "bank", "deaths"]:
        logger.warning("Rejected invalid sort field: %s", field)
        return []
    cursor = economy_col.find({}).sort(field, -1).limit(limit)
    return [doc async for doc in cursor]


# ── Group Helpers ────────────────────────────
async def add_group(chat_id: int, title: str) -> None:
    """Register or update a group."""
    await groups_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id, "title": title}},
        upsert=True,
    )


async def add_user(user_id: int, name: str) -> None:
    """Register or update a user."""
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "name": name}},
        upsert=True,
    )


async def get_all_groups() -> list[int]:
    """Return all registered group chat_ids."""
    cursor = groups_col.find({}, {"chat_id": 1, "_id": 0})
    return [doc["chat_id"] async for doc in cursor]


async def get_total_users() -> int:
    """Count total registered users."""
    return await users_col.count_documents({})


async def get_total_groups() -> int:
    """Count total registered groups."""
    return await groups_col.count_documents({})


# ── Stats Helpers ────────────────────────────
async def increment_stat(key: str, value: int = 1) -> None:
    """Increment a global stat counter."""
    await stats_col.update_one(
        {"key": key},
        {"$inc": {"value": value}},
        upsert=True,
    )


async def get_stat(key: str) -> int:
    """Get the current value of a stat counter."""
    doc = await stats_col.find_one({"key": key})
    return doc["value"] if doc else 0


# ── Global Ban Helpers ───────────────────────
async def gban_user(user_id: int, reason: str = "") -> None:
    """Globally ban a user."""
    await gban_col.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "reason": reason, "time": int(time.time())}},
        upsert=True,
    )

async def ungban_user(user_id: int) -> None:
    """Remove global ban."""
    await gban_col.delete_one({"user_id": user_id})

async def is_gbanned(user_id: int) -> bool:
    """Check if user is globally banned."""
    return await gban_col.find_one({"user_id": user_id}) is not None

async def get_gban_list() -> list[dict]:
    """Get all gbanned users."""
    return [doc async for doc in gban_col.find({})]


# ── Warning Helpers ──────────────────────────
async def add_warning(chat_id: int, user_id: int, reason: str = "") -> int:
    """Add a warning. Returns total warnings."""
    await warnings_col.insert_one({
        "chat_id": chat_id, "user_id": user_id,
        "reason": reason, "time": int(time.time()),
    })
    return await warnings_col.count_documents({"chat_id": chat_id, "user_id": user_id})

async def remove_warning(chat_id: int, user_id: int) -> bool:
    """Remove the oldest warning. Returns True if removed."""
    doc = await warnings_col.find_one(
        {"chat_id": chat_id, "user_id": user_id},
        sort=[("time", 1)]
    )
    if doc:
        await warnings_col.delete_one({"_id": doc["_id"]})
        return True
    return False

async def get_warnings(chat_id: int, user_id: int) -> list[dict]:
    """Get all warnings for a user in a chat."""
    cursor = warnings_col.find({"chat_id": chat_id, "user_id": user_id}).sort("time", -1)
    return [doc async for doc in cursor]

async def clear_warnings(chat_id: int, user_id: int) -> int:
    """Clear all warnings. Returns count deleted."""
    result = await warnings_col.delete_many({"chat_id": chat_id, "user_id": user_id})
    return result.deleted_count


# ── Inventory Helpers ────────────────────────
async def add_inventory_item(user_id: int, item: str) -> None:
    """Add an item to user inventory."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$push": {"inventory": item}},
    )
    _doc_cache.delete(f"eco_{user_id}")

async def remove_inventory_item(user_id: int, item: str) -> bool:
    """Remove one instance of an item. Returns True if found."""
    doc = await get_user_economy(user_id)
    inv = doc.get("inventory", [])
    if item in inv:
        await economy_col.update_one(
            {"user_id": user_id, "inventory": item},
            {"$pull": {"inventory": item}},
        )
        # Re-add extras if there were duplicates (pull removes all)
        count = inv.count(item) - 1
        if count > 0:
            await economy_col.update_one(
                {"user_id": user_id},
                {"$push": {"inventory": {"$each": [item] * count}}},
            )
        _doc_cache.delete(f"eco_{user_id}")
        return True
    return False


# ── AFK Helpers ──────────────────────────────
async def set_afk(user_id: int, reason: str = "AFK") -> None:
    """Set AFK status."""
    await ensure_user(user_id)
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"afk": reason[:100], "afk_time": int(time.time())}},
    )
    _doc_cache.delete(f"eco_{user_id}")

async def clear_afk(user_id: int) -> None:
    """Clear AFK status."""
    await economy_col.update_one(
        {"user_id": user_id},
        {"$set": {"afk": "", "afk_time": 0}},
    )
    _doc_cache.delete(f"eco_{user_id}")


# ── Marriage Helpers ─────────────────────────
async def set_partner(user_id: int, partner_id: int) -> None:
    """Set marriage partner for both users."""
    await ensure_user(user_id)
    await ensure_user(partner_id)
    await economy_col.update_one({"user_id": user_id}, {"$set": {"partner_id": partner_id}})
    await economy_col.update_one({"user_id": partner_id}, {"$set": {"partner_id": user_id}})
    _doc_cache.delete(f"eco_{user_id}")
    _doc_cache.delete(f"eco_{partner_id}")

async def clear_partner(user_id: int) -> None:
    """Divorce — clear partner for both users."""
    doc = await get_user_economy(user_id)
    partner_id = doc.get("partner_id", 0)
    await economy_col.update_one({"user_id": user_id}, {"$set": {"partner_id": 0}})
    if partner_id:
        await economy_col.update_one({"user_id": partner_id}, {"$set": {"partner_id": 0}})
        _doc_cache.delete(f"eco_{partner_id}")
    _doc_cache.delete(f"eco_{user_id}")


# ── XP & Level Helpers ──────────────────────
async def add_xp(user_id: int, amount: int) -> dict:
    """Add XP and auto-level-up. Returns {leveled_up, new_level, xp}."""
    await ensure_user(user_id)
    await economy_col.update_one({"user_id": user_id}, {"$inc": {"xp": amount}})
    _doc_cache.delete(f"eco_{user_id}")
    doc = await get_user_economy(user_id)
    xp = doc.get("xp", 0)
    level = doc.get("level", 1)
    # Level formula: need level * 500 XP to level up
    needed = level * 500
    leveled = False
    while xp >= needed:
        xp -= needed
        level += 1
        needed = level * 500
        leveled = True
    if leveled:
        await economy_col.update_one(
            {"user_id": user_id},
            {"$set": {"level": level, "xp": xp}}
        )
        _doc_cache.delete(f"eco_{user_id}")
    return {"leveled_up": leveled, "new_level": level, "xp": xp}


# ── Game Stats Helpers ───────────────────────
async def update_game_stats(user_id: int, won: bool) -> None:
    """Track game win/loss."""
    field = "games_won" if won else "games_lost"
    await economy_col.update_one(
        {"user_id": user_id},
        {"$inc": {field: 1}},
    )
    _doc_cache.delete(f"eco_{user_id}")


# ── Dynamic Config Helpers ───────────────────
async def set_dynamic_config(key: str, value) -> None:
    """Set a dynamic config value (persisted to DB)."""
    await stats_col.update_one(
        {"key": f"config_{key}"},
        {"$set": {"key": f"config_{key}", "value": value}},
        upsert=True,
    )

async def get_dynamic_config(key: str, default=None):
    """Get a dynamic config value."""
    doc = await stats_col.find_one({"key": f"config_{key}"})
    return doc["value"] if doc else default


# Music Settings Helpers
async def get_music_settings(chat_id: int) -> dict:
    """Get per-chat music settings, creating defaults if missing."""
    doc = await music_settings_col.find_one({"chat_id": chat_id})
    if doc:
        return {**_DEFAULT_MUSIC_SETTINGS, **doc}

    new_doc = {"chat_id": chat_id, **_DEFAULT_MUSIC_SETTINGS}
    await music_settings_col.insert_one(new_doc)
    return dict(new_doc)


async def set_music_setting(chat_id: int, key: str, value):
    """Update one music setting key."""
    if key not in _DEFAULT_MUSIC_SETTINGS:
        return
    await music_settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id, key: value}},
        upsert=True,
    )


async def update_music_settings(chat_id: int, updates: dict):
    """Bulk update allowed music settings."""
    safe = {k: v for k, v in updates.items() if k in _DEFAULT_MUSIC_SETTINGS}
    if not safe:
        return
    safe["chat_id"] = chat_id
    await music_settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": safe},
        upsert=True,
    )


# Playlist Helpers
async def save_chat_playlist(chat_id: int, name: str, tracks: list[dict], created_by: int) -> None:
    """Save or replace a chat playlist."""
    clean_name = (name or "").strip().lower()[:32]
    if not clean_name:
        return
    await playlists_col.update_one(
        {"chat_id": chat_id, "name": clean_name},
        {
            "$set": {
                "chat_id": chat_id,
                "name": clean_name,
                "tracks": tracks[:100],
                "created_by": created_by,
                "updated_at": int(time.time()),
            }
        },
        upsert=True,
    )


async def get_chat_playlist(chat_id: int, name: str) -> dict | None:
    """Get a named chat playlist."""
    clean_name = (name or "").strip().lower()[:32]
    if not clean_name:
        return None
    return await playlists_col.find_one({"chat_id": chat_id, "name": clean_name})


async def list_chat_playlists(chat_id: int, limit: int = 20) -> list[dict]:
    """List chat playlists."""
    cursor = playlists_col.find({"chat_id": chat_id}).sort("updated_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def delete_chat_playlist(chat_id: int, name: str) -> bool:
    """Delete playlist by name."""
    clean_name = (name or "").strip().lower()[:32]
    if not clean_name:
        return False
    result = await playlists_col.delete_one({"chat_id": chat_id, "name": clean_name})
    return result.deleted_count > 0


# Music History / Stats Helpers
def _track_key(title: str, url: str) -> str:
    base = (title or url or "unknown").strip().lower()
    return base[:200]


async def record_track_play(chat_id: int, track: dict):
    """Persist lightweight play history and aggregate counters."""
    title = track.get("title", "Unknown")
    url = track.get("url", "")
    requested_by = int(track.get("requested_by", 0) or 0)
    now_ts = int(time.time())
    key = _track_key(title, url)

    await music_history_col.insert_one(
        {
            "chat_id": chat_id,
            "track_key": key,
            "title": title[:128],
            "url": url,
            "requested_by": requested_by,
            "played_at": now_ts,
        }
    )

    await stats_col.update_one(
        {"key": f"chat_track_{chat_id}_{key}"},
        {
            "$inc": {"count": 1},
            "$set": {"title": title[:128], "chat_id": chat_id, "last_played_at": now_ts},
        },
        upsert=True,
    )


async def get_chat_history(chat_id: int, limit: int = 10) -> list[dict]:
    """Get recent played tracks for a chat."""
    cursor = music_history_col.find({"chat_id": chat_id}).sort("played_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_chat_top_tracks(chat_id: int, limit: int = 10) -> list[dict]:
    """Get top tracks for a chat from aggregated stat documents."""
    prefix = f"chat_track_{chat_id}_"
    cursor = stats_col.find({"key": {"$regex": f"^{prefix}"}}).sort("count", -1).limit(limit)
    return [doc async for doc in cursor]


# Sudo ACL Helpers
async def approve_sudo_user(user_id: int, username: str = "", approved_by: int = 0):
    """Approve a user for SUDO privileges."""
    await sudo_users_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "username": (username or "").lower(),
                "approved_by": approved_by,
                "approved_at": int(time.time()),
            }
        },
        upsert=True,
    )


async def unapprove_sudo_user(user_id: int) -> bool:
    """Remove a user from dynamic SUDO ACL."""
    result = await sudo_users_col.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def get_approved_sudo_ids() -> list[int]:
    """Return all dynamic SUDO user IDs."""
    cursor = sudo_users_col.find({}, {"user_id": 1, "_id": 0})
    return [int(doc["user_id"]) async for doc in cursor if "user_id" in doc]


async def get_approved_sudo_users(limit: int = 200) -> list[dict]:
    """Return dynamic SUDO user documents."""
    cursor = sudo_users_col.find({}).sort("approved_at", -1).limit(limit)
    return [doc async for doc in cursor]


# Global Instance Lock Helpers
async def acquire_global_instance_lock(instance_id: str, meta: dict | None = None, ttl_seconds: int = 120) -> bool:
    """
    Acquire a global singleton lock for this bot process.
    Returns True if lock is acquired by this instance, False if another is active.
    """
    now = int(time.time())
    expires_at = now + max(30, int(ttl_seconds))
    payload = {
        "_id": "global_bot_instance",
        "instance_id": instance_id,
        "updated_at": now,
        "expires_at": expires_at,
        "meta": meta or {},
    }

    doc = await instance_lock_col.find_one_and_update(
        {
            "_id": "global_bot_instance",
            "$or": [
                {"instance_id": instance_id},
                {"expires_at": {"$lt": now}},
                {"expires_at": {"$exists": False}},
            ],
        },
        {"$set": payload},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return bool(doc and doc.get("instance_id") == instance_id)


async def renew_global_instance_lock(instance_id: str, ttl_seconds: int = 120) -> bool:
    """Refresh lock heartbeat. Returns False if lock ownership was lost."""
    now = int(time.time())
    expires_at = now + max(30, int(ttl_seconds))
    result = await instance_lock_col.update_one(
        {"_id": "global_bot_instance", "instance_id": instance_id},
        {"$set": {"updated_at": now, "expires_at": expires_at}},
    )
    return result.modified_count > 0


async def release_global_instance_lock(instance_id: str) -> None:
    """Release singleton lock if owned by this instance."""
    await instance_lock_col.delete_one({"_id": "global_bot_instance", "instance_id": instance_id})


async def get_global_instance_lock() -> dict | None:
    """Get current lock document for diagnostics."""
    return await instance_lock_col.find_one({"_id": "global_bot_instance"})

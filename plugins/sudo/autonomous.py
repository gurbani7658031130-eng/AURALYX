"""Autonomous operations pack: autoclean, autowarn, safeurl, autoleave, backup auto, incident panel, selftest, autobroadcast."""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone

from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait
from pyrogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.maintenance import set_maintenance
from core.sudo_acl import is_sudo
from database.approval_sqlite import init_db as init_approval_db
from database.mongo import db, get_all_groups, get_dynamic_config, set_dynamic_config
from utils.decorators import error_handler, sudo_only
from utils.queue import active_queue_count, _queues
from utils.resource_guard import get_resource_stats
from utils.stream import cleanup_all

logger = logging.getLogger(__name__)

_MONITOR_CACHE_TTL = 30
_chat_cfg_cache: dict[int, tuple[dict, float]] = {}
_warn_hits: dict[tuple[int, int], list[float]] = {}  # (chat_id,user_id) -> timestamps
_workers_started = False
_worker_tasks: list[asyncio.Task] = []
_runtime_client: Client | None = None
_incident_sessions: dict[int, dict] = {}  # msg_id -> owner/timestamp

_URL_RE = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+", re.IGNORECASE)
_SUSPICIOUS_DOMAIN_RE = re.compile(r"(?:bit\.ly|tinyurl\.com|t\.me/\+|telegram\.me/joinchat)", re.IGNORECASE)


def _default_chat_cfg() -> dict:
    return {
        "autoclean": {"enabled": False, "ttl": 20},
        "autowarn": {"enabled": False, "threshold": 4, "window": 12},
        "safeurl": {"enabled": False},
    }


async def _get_chat_cfg(chat_id: int) -> dict:
    now = time.monotonic()
    cached = _chat_cfg_cache.get(chat_id)
    if cached and now < cached[1]:
        return dict(cached[0])

    cfg = await get_dynamic_config(f"auto_chat_{chat_id}", default=None)
    if not isinstance(cfg, dict):
        cfg = _default_chat_cfg()
    # ensure all keys exist
    base = _default_chat_cfg()
    for k, v in base.items():
        if k not in cfg or not isinstance(cfg[k], dict):
            cfg[k] = v
    _chat_cfg_cache[chat_id] = (dict(cfg), now + _MONITOR_CACHE_TTL)
    return cfg


async def _set_chat_cfg(chat_id: int, cfg: dict):
    await set_dynamic_config(f"auto_chat_{chat_id}", cfg)
    _chat_cfg_cache[chat_id] = (dict(cfg), time.monotonic() + _MONITOR_CACHE_TTL)


def _schedule_delete(client: Client, chat_id: int, message_id: int, delay: int):
    async def _job():
        try:
            await asyncio.sleep(max(1, delay))
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass

    asyncio.create_task(_job())


def _is_suspicious_url(text: str) -> bool:
    if not text:
        return False
    if _SUSPICIOUS_DOMAIN_RE.search(text):
        return True
    # generic invite patterns
    return "t.me/+" in text.lower() or "joinchat" in text.lower()


def _looks_like_caps_spam(text: str) -> bool:
    if not text or len(text) < 14:
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    uppers = [c for c in letters if c.isupper()]
    return (len(uppers) / len(letters)) >= 0.8


def _mention_count(message: Message) -> int:
    count = 0
    if message.entities:
        for e in message.entities:
            if e.type in {enums.MessageEntityType.MENTION, enums.MessageEntityType.TEXT_MENTION}:
                count += 1
    return count


async def _ensure_workers(client: Client):
    global _workers_started, _runtime_client
    _runtime_client = client
    if _workers_started:
        return
    _workers_started = True
    _worker_tasks.append(asyncio.create_task(_autobroadcast_worker()))
    _worker_tasks.append(asyncio.create_task(_autobackup_worker()))


async def _autobroadcast_worker():
    """Periodic global broadcast worker driven by dynamic config."""
    while True:
        try:
            cfg = await get_dynamic_config("autobroadcast", default={"enabled": False, "interval_min": 120, "text": ""})
            if not isinstance(cfg, dict):
                cfg = {"enabled": False, "interval_min": 120, "text": ""}

            if not cfg.get("enabled"):
                await asyncio.sleep(20)
                continue

            interval_min = int(cfg.get("interval_min", 120))
            interval_min = max(5, min(interval_min, 1440))
            text = str(cfg.get("text", "")).strip()
            if not text:
                await asyncio.sleep(20)
                continue

            if _runtime_client is None:
                await asyncio.sleep(10)
                continue

            stats = await _run_autobroadcast_now(_runtime_client)

            await set_dynamic_config("autobroadcast_last_run", int(time.time()))
            await set_dynamic_config("autobroadcast_last_stats", stats)
            await asyncio.sleep(interval_min * 60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("autobroadcast worker error: %s", e)
            await asyncio.sleep(30)


async def _run_autobroadcast_now(client: Client):
    cfg = await get_dynamic_config("autobroadcast", default={"enabled": False, "interval_min": 120, "text": ""})
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return {"sent": 0, "failed": 0, "groups": 0}
    text = str(cfg.get("text", "")).strip()
    if not text:
        return {"sent": 0, "failed": 0, "groups": 0}

    groups = await get_all_groups()
    sent = 0
    failed = 0
    for chat_id in groups:
        try:
            await client.send_message(chat_id, text)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await client.send_message(chat_id, text)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.2)

    await set_dynamic_config("autobroadcast_last_run", int(time.time()))
    await set_dynamic_config("autobroadcast_last_stats", {"sent": sent, "failed": failed, "groups": len(groups)})
    return {"sent": sent, "failed": failed, "groups": len(groups)}


async def _autobackup_worker():
    while True:
        try:
            cfg = await get_dynamic_config("autobackup", default={"enabled": False, "interval_h": 6, "keep": 5})
            if not isinstance(cfg, dict) or not cfg.get("enabled"):
                await asyncio.sleep(30)
                continue

            interval_h = int(cfg.get("interval_h", 6))
            keep = int(cfg.get("keep", 5))
            interval_h = max(1, min(interval_h, 24 * 7))
            keep = max(1, min(keep, 20))

            await _create_backup_snapshot(keep=keep)
            await asyncio.sleep(interval_h * 3600)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("autobackup worker error: %s", e)
            await asyncio.sleep(60)


async def _create_backup_snapshot(keep: int = 5) -> str:
    backup_dir = os.path.join(os.getcwd(), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, f"snapshot_{stamp}.json")

    payload = {"created_at": int(time.time()), "collections": {}}
    # lightweight core collections
    names = ["groups", "users", "economy", "stats", "gbans", "warnings", "music_settings", "playlists", "music_history"]
    for name in names:
        try:
            cursor = db[name].find({}).limit(50000)
            rows = []
            async for doc in cursor:
                doc.pop("_id", None)
                rows.append(doc)
            payload["collections"][name] = rows
        except Exception as e:
            payload["collections"][name] = {"error": str(e)}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # include SQLite approval DB copy
    sqlite_src = os.path.join(os.getcwd(), "database", "approved_users.db")
    if os.path.exists(sqlite_src):
        try:
            shutil.copy2(sqlite_src, os.path.join(backup_dir, f"approved_users_{stamp}.db"))
        except Exception:
            pass

    # retention cleanup
    files = sorted(
        [os.path.join(backup_dir, x) for x in os.listdir(backup_dir)],
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    for old in files[keep * 2 :]:
        try:
            os.remove(old)
        except Exception:
            pass

    await set_dynamic_config("autobackup_last_run", int(time.time()))
    return path


@Client.on_message(filters.command("autoclean") & filters.group)
@error_handler
@sudo_only
async def autoclean_command(client: Client, message: Message):
    await _ensure_workers(client)
    cfg = await _get_chat_cfg(message.chat.id)

    if len(message.command) < 2:
        ac = cfg.get("autoclean", {})
        return await message.reply_text(
            f"AutoClean: {'ON' if ac.get('enabled') else 'OFF'} | ttl={ac.get('ttl', 20)}s\nUsage: /autoclean on|off [seconds]",
            quote=True,
        )

    mode = message.command[1].lower()
    if mode not in {"on", "off"}:
        return await message.reply_text("Usage: /autoclean on|off [seconds]", quote=True)

    ttl = cfg.get("autoclean", {}).get("ttl", 20)
    if len(message.command) > 2 and message.command[2].isdigit():
        ttl = max(5, min(int(message.command[2]), 300))

    cfg["autoclean"] = {"enabled": mode == "on", "ttl": ttl}
    await _set_chat_cfg(message.chat.id, cfg)
    await message.reply_text(f"AutoClean set to {mode.upper()} (ttl={ttl}s)", quote=True)


@Client.on_message(filters.command("autowarn") & filters.group)
@error_handler
@sudo_only
async def autowarn_command(client: Client, message: Message):
    await _ensure_workers(client)
    cfg = await _get_chat_cfg(message.chat.id)

    if len(message.command) < 2:
        aw = cfg.get("autowarn", {})
        return await message.reply_text(
            f"AutoWarn: {'ON' if aw.get('enabled') else 'OFF'} | threshold={aw.get('threshold', 4)} window={aw.get('window', 12)}s\n"
            "Usage: /autowarn on|off [threshold] [window_sec]",
            quote=True,
        )

    mode = message.command[1].lower()
    if mode not in {"on", "off"}:
        return await message.reply_text("Usage: /autowarn on|off [threshold] [window_sec]", quote=True)

    threshold = cfg.get("autowarn", {}).get("threshold", 4)
    window = cfg.get("autowarn", {}).get("window", 12)
    if len(message.command) > 2 and message.command[2].isdigit():
        threshold = max(2, min(int(message.command[2]), 10))
    if len(message.command) > 3 and message.command[3].isdigit():
        window = max(5, min(int(message.command[3]), 120))

    cfg["autowarn"] = {"enabled": mode == "on", "threshold": threshold, "window": window}
    await _set_chat_cfg(message.chat.id, cfg)
    await message.reply_text(f"AutoWarn set to {mode.upper()} (threshold={threshold}, window={window}s)", quote=True)


@Client.on_message(filters.command("safeurl") & filters.group)
@error_handler
@sudo_only
async def safeurl_command(client: Client, message: Message):
    await _ensure_workers(client)
    cfg = await _get_chat_cfg(message.chat.id)

    if len(message.command) < 2:
        su = cfg.get("safeurl", {})
        return await message.reply_text(f"SafeURL: {'ON' if su.get('enabled') else 'OFF'}\nUsage: /safeurl on|off", quote=True)

    mode = message.command[1].lower()
    if mode not in {"on", "off"}:
        return await message.reply_text("Usage: /safeurl on|off", quote=True)

    cfg["safeurl"] = {"enabled": mode == "on"}
    await _set_chat_cfg(message.chat.id, cfg)
    await message.reply_text(f"SafeURL set to {mode.upper()}", quote=True)


@Client.on_message(filters.command("autoleave") & (filters.private | filters.group))
@error_handler
@sudo_only
async def autoleave_command(client: Client, message: Message):
    """Manual run: /autoleave inactive <days>"""
    await _ensure_workers(client)
    if len(message.command) < 3 or message.command[1].lower() != "inactive" or not message.command[2].isdigit():
        return await message.reply_text("Usage: /autoleave inactive <days>", quote=True)

    days = max(1, min(int(message.command[2]), 365))
    cutoff = time.time() - (days * 86400)

    groups = await get_all_groups()
    left = 0
    failed = 0

    status = await message.reply_text(f"Scanning {len(groups)} chats for inactivity > {days} days...", quote=True)

    for i, chat_id in enumerate(groups, start=1):
        try:
            msg = await client.get_messages(chat_id, 1)
            if msg and getattr(msg, "date", None):
                ts = msg.date.timestamp()
                if ts < cutoff:
                    await client.leave_chat(chat_id)
                    left += 1
            else:
                await client.leave_chat(chat_id)
                left += 1
        except Exception:
            failed += 1

        if i % 50 == 0:
            try:
                await status.edit_text(f"AutoLeave scan... {i}/{len(groups)} | left={left} failed={failed}")
            except Exception:
                pass

    await status.edit_text(f"AutoLeave complete. Left={left}, Failed={failed}")


@Client.on_message(filters.command(["backupauto", "backup_auto"]) & (filters.private | filters.group))
@error_handler
@sudo_only
async def backup_auto_command(client: Client, message: Message):
    """/backupauto on|off [interval_h] [keep]"""
    await _ensure_workers(client)
    cfg = await get_dynamic_config("autobackup", default={"enabled": False, "interval_h": 6, "keep": 5})
    if not isinstance(cfg, dict):
        cfg = {"enabled": False, "interval_h": 6, "keep": 5}

    if len(message.command) < 2:
        return await message.reply_text(
            f"BackupAuto: {'ON' if cfg.get('enabled') else 'OFF'} | every={cfg.get('interval_h', 6)}h keep={cfg.get('keep', 5)}\n"
            "Usage: /backupauto on|off [interval_h] [keep]",
            quote=True,
        )

    mode = message.command[1].lower()
    if mode not in {"on", "off"}:
        return await message.reply_text("Usage: /backupauto on|off [interval_h] [keep]", quote=True)

    interval_h = int(cfg.get("interval_h", 6))
    keep = int(cfg.get("keep", 5))
    if len(message.command) > 2 and message.command[2].isdigit():
        interval_h = max(1, min(int(message.command[2]), 168))
    if len(message.command) > 3 and message.command[3].isdigit():
        keep = max(1, min(int(message.command[3]), 20))

    cfg = {"enabled": mode == "on", "interval_h": interval_h, "keep": keep}
    await set_dynamic_config("autobackup", cfg)
    await message.reply_text(f"BackupAuto set to {mode.upper()} (every {interval_h}h, keep {keep})", quote=True)


@Client.on_message(filters.command("incident") & (filters.private | filters.group))
@error_handler
@sudo_only
async def incident_command(client: Client, message: Message):
    await _ensure_workers(client)
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Maint ON", callback_data="inc:maint_on"),
                InlineKeyboardButton("Maint OFF", callback_data="inc:maint_off"),
            ],
            [
                InlineKeyboardButton("Drain ON", callback_data="inc:drain_on"),
                InlineKeyboardButton("Drain OFF", callback_data="inc:drain_off"),
            ],
            [
                InlineKeyboardButton("Cleanup", callback_data="inc:cleanup"),
                InlineKeyboardButton("LeaveAll", callback_data="inc:leaveall"),
            ],
            [InlineKeyboardButton("Close", callback_data="inc:close")],
        ]
    )
    sent = await message.reply_text("INCIDENT PANEL", quote=True, reply_markup=markup)
    _incident_sessions[sent.id] = {"owner": message.from_user.id if message.from_user else 0, "exp": time.time() + 900}


@Client.on_callback_query(filters.regex(r"^inc:(maint_on|maint_off|drain_on|drain_off|cleanup|leaveall|close)$"))
async def incident_callback(client: Client, callback: CallbackQuery):
    if not callback.from_user:
        return await callback.answer("Invalid user", show_alert=True)

    sess = _incident_sessions.get(callback.message.id)
    if not sess or time.time() > sess.get("exp", 0):
        _incident_sessions.pop(callback.message.id, None)
        return await callback.answer("Incident panel expired", show_alert=True)

    if not await is_sudo(callback.from_user.id):
        return await callback.answer("Only owner/static sudo", show_alert=True)

    action = callback.data.split(":", 1)[1]
    if action == "close":
        _incident_sessions.pop(callback.message.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await callback.answer("Closed")

    if action == "maint_on":
        await set_maintenance(True)
        return await callback.answer("Maintenance ON", show_alert=True)
    if action == "maint_off":
        await set_maintenance(False)
        return await callback.answer("Maintenance OFF", show_alert=True)
    if action == "drain_on":
        await set_dynamic_config("drain_mode", True)
        return await callback.answer("Drain ON", show_alert=True)
    if action == "drain_off":
        await set_dynamic_config("drain_mode", False)
        return await callback.answer("Drain OFF", show_alert=True)
    if action == "cleanup":
        await cleanup_all()
        _queues.clear()
        return await callback.answer("Cleanup done", show_alert=True)
    if action == "leaveall":
        from core.assistant import assistant

        groups = await get_all_groups()
        left = 0
        for chat_id in groups:
            try:
                await assistant.leave_chat(chat_id)
                left += 1
            except Exception:
                pass
        return await callback.answer(f"Left {left} chats", show_alert=True)


@Client.on_message(filters.command("selftest") & (filters.private | filters.group))
@error_handler
@sudo_only
async def selftest_command(client: Client, message: Message):
    await _ensure_workers(client)
    lines = ["SELFTEST"]

    # Mongo
    try:
        await db.command("ping")
        lines.append("Mongo: OK")
    except Exception as e:
        lines.append(f"Mongo: FAIL ({e})")

    # SQLite
    try:
        await init_approval_db()
        lines.append("SQLite approvals: OK")
    except Exception as e:
        lines.append(f"SQLite approvals: FAIL ({e})")

    # Assistant
    try:
        from core.assistant import assistant

        me = await assistant.get_me()
        lines.append(f"Assistant: OK ({me.id})")
    except Exception as e:
        lines.append(f"Assistant: FAIL ({e})")

    # Resources
    try:
        res = get_resource_stats()
        lines.append(f"CPU: {res.get('cpu', 0)}% | RAM: {res.get('ram_percent', 0)}%")
    except Exception as e:
        lines.append(f"Resources: FAIL ({e})")

    lines.append(f"Active Queues: {active_queue_count()}")

    drain = await get_dynamic_config("drain_mode", default=False)
    lines.append(f"Drain Mode: {'ON' if drain else 'OFF'}")

    ab = await get_dynamic_config("autobroadcast", default={"enabled": False})
    bk = await get_dynamic_config("autobackup", default={"enabled": False})
    lines.append(f"AutoBroadcast: {'ON' if isinstance(ab, dict) and ab.get('enabled') else 'OFF'}")
    lines.append(f"AutoBackup: {'ON' if isinstance(bk, dict) and bk.get('enabled') else 'OFF'}")

    await message.reply_text("\n".join(lines), quote=True)


@Client.on_message(filters.command("autobroadcast") & (filters.private | filters.group))
@error_handler
@sudo_only
async def autobroadcast_command(client: Client, message: Message):
    """/autobroadcast on <interval_min> <text> | /autobroadcast off | /autobroadcast now"""
    await _ensure_workers(client)
    if len(message.command) < 2:
        cfg = await get_dynamic_config("autobroadcast", default={"enabled": False, "interval_min": 120, "text": ""})
        if not isinstance(cfg, dict):
            cfg = {"enabled": False, "interval_min": 120, "text": ""}
        return await message.reply_text(
            f"AutoBroadcast: {'ON' if cfg.get('enabled') else 'OFF'} | every={cfg.get('interval_min', 120)}m\n"
            "Usage:\n"
            "/autobroadcast on <interval_min> <text>\n"
            "/autobroadcast off\n"
            "/autobroadcast now",
            quote=True,
        )

    sub = message.command[1].lower()
    if sub == "off":
        await set_dynamic_config("autobroadcast", {"enabled": False, "interval_min": 120, "text": ""})
        return await message.reply_text("AutoBroadcast OFF", quote=True)

    if sub == "now":
        status = await message.reply_text("Running autobroadcast now...", quote=True)
        stats = await _run_autobroadcast_now(client)
        return await status.edit_text(
            f"AutoBroadcast NOW done. Groups={stats['groups']} Sent={stats['sent']} Failed={stats['failed']}"
        )

    if sub == "on":
        if len(message.command) < 4:
            return await message.reply_text("Usage: /autobroadcast on <interval_min> <text>", quote=True)
        if not message.command[2].isdigit():
            return await message.reply_text("interval_min must be number", quote=True)
        interval_min = max(5, min(int(message.command[2]), 1440))
        text = message.text.split(None, 3)[3].strip()
        if not text:
            return await message.reply_text("Broadcast text cannot be empty", quote=True)
        await set_dynamic_config(
            "autobroadcast",
            {"enabled": True, "interval_min": interval_min, "text": text[:3500]},
        )
        return await message.reply_text(f"AutoBroadcast ON every {interval_min}m", quote=True)

    await message.reply_text("Usage: /autobroadcast on|off|now ...", quote=True)


@Client.on_message(filters.group, group=95)
async def automation_monitor(client: Client, message: Message):
    """Passive monitor for autoclean/autowarn/safeurl."""
    if not message or not message.chat or not message.from_user:
        return

    await _ensure_workers(client)
    cfg = await _get_chat_cfg(message.chat.id)

    # 1) AutoClean: delete command messages after ttl.
    ac = cfg.get("autoclean", {})
    if ac.get("enabled") and (message.text or "").startswith("/"):
        ttl = int(ac.get("ttl", 20))
        _schedule_delete(client, message.chat.id, message.id, ttl)

    # Skip moderation checks for owner/static sudo/admins
    if await is_sudo(message.from_user.id):
        return

    text = (message.text or message.caption or "")

    # 2) SafeURL
    su = cfg.get("safeurl", {})
    if su.get("enabled") and _URL_RE.search(text) and _is_suspicious_url(text):
        try:
            await message.delete()
        except Exception:
            pass
        try:
            warn = await message.reply_text("Suspicious URL blocked.", quote=True)
            _schedule_delete(client, message.chat.id, warn.id, 15)
        except Exception:
            pass
        return

    # 3) AutoWarn heuristics
    aw = cfg.get("autowarn", {})
    if not aw.get("enabled"):
        return

    hit = False
    # a) caps spam
    if _looks_like_caps_spam(text):
        hit = True
    # b) mention spam
    if _mention_count(message) >= 5:
        hit = True

    # c) flood burst tracker
    key = (message.chat.id, message.from_user.id)
    now = time.time()
    window = int(aw.get("window", 12))
    threshold = int(aw.get("threshold", 4))

    arr = _warn_hits.get(key, [])
    arr = [t for t in arr if now - t <= window]
    arr.append(now)
    _warn_hits[key] = arr
    if len(arr) >= threshold:
        hit = True

    if hit:
        try:
            await message.delete()
        except Exception:
            pass
        try:
            from database.mongo import add_warning

            total = await add_warning(message.chat.id, message.from_user.id, "AutoWarn trigger")
            note = await message.reply_text(
                f"AutoWarn: user `{message.from_user.id}` warned. Total warnings: {total}",
                quote=True,
            )
            _schedule_delete(client, message.chat.id, note.id, 20)
        except Exception:
            pass

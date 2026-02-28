"""
Auralyx Music - Music Player
"""

import asyncio
import logging
import time
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import MAX_DURATION, SUDO_USERS
from core.permissions import is_admin
from core.voice_cleanup import record_activity
from database.mongo import get_dynamic_config, increment_stat, record_track_play
from utils.decorators import error_handler, rate_limit
from utils.music_settings import fetch_settings
from utils.queue import add_to_queue, get_queue, has_duplicate, queue_size

logger = logging.getLogger(__name__)
_play_dedupe: dict[tuple[int, int], float] = {}
_search_cache: dict[tuple[int, int], tuple[float, list[dict]]] = {}
_extract_cache: dict[tuple[str, bool], tuple[float, dict]] = {}
_stream_resolve_cache: dict[tuple[str, bool], tuple[float, str]] = {}


def _is_duplicate_play(chat_id: int, message_id: int, ttl: int = 30) -> bool:
    """Return True if this play message was already processed recently."""
    now = time.monotonic()
    for key, ts in list(_play_dedupe.items()):
        if now - ts > ttl:
            _play_dedupe.pop(key, None)

    key = (chat_id, message_id)
    if key in _play_dedupe:
        return True
    _play_dedupe[key] = now
    return False


async def _extract_info(query: str, video: bool = False) -> dict | None:
    """Extract song/video info using yt-dlp."""
    try:
        cache_key = (query.strip().lower(), video)
        now = time.monotonic()
        cached = _extract_cache.get(cache_key)
        if cached and (now - cached[0] < 120):
            return dict(cached[1])

        import yt_dlp

        def run_extraction():
            ydl_opts = {
                "format": (
                    "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best"
                    if not video
                    else "best[height<=360][vcodec!=none][acodec!=none]/best"
                ),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "default_search": "ytsearch",
                "cachedir": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_query = query if query.startswith("http") else f"ytsearch:{query}"
                info = ydl.extract_info(search_query, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                return {
                    "title": info.get("title", "Unknown"),
                    "url": info.get("url"),
                    "webpage_url": info.get("webpage_url") or info.get("original_url") or query,
                    "duration": info.get("duration", 0),
                    "thumbnail": info.get("thumbnail"),
                    "is_video": video,
                }

        result = await asyncio.to_thread(run_extraction)
        _extract_cache[cache_key] = (now, dict(result))
        return result
    except Exception as e:
        logger.error("Extraction error: %s", e)
        return None


def _is_direct_stream_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        token in u
        for token in ("googlevideo.com", ".m3u8", ".mpd", ".flv", ".m4a", ".mp3", ".aac", ".ogg", ".opus")
    )


async def _resolve_stream_url(url: str, is_video: bool = False) -> str | None:
    """Resolve a watch URL to a direct media stream URL when needed."""
    if not url:
        return None
    if _is_direct_stream_url(url):
        return url

    cache_key = (url, is_video)
    now = time.monotonic()
    cached = _stream_resolve_cache.get(cache_key)
    if cached and (now - cached[0] < 120):
        return cached[1]

    try:
        import yt_dlp

        def run_resolve():
            opts = {
                "format": (
                    "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best"
                    if not is_video
                    else "best[height<=360][vcodec!=none][acodec!=none]/best"
                ),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                return info.get("url")

        direct = await asyncio.to_thread(run_resolve)
        if direct:
            _stream_resolve_cache[cache_key] = (now, direct)
            return direct
    except Exception as e:
        logger.warning("Stream URL resolve failed for %s: %s", url, e)
    return url


async def _start_stream(client: Client, chat_id: int, stream_url: str, is_video: bool = False) -> tuple[bool, str]:
    """Start direct streaming using PyTgCalls helpers."""
    from core.assistant import assistant
    from core.call import call_manager

    try:
        record_activity(chat_id)

        # Ensure assistant is in group.
        try:
            await assistant.get_chat_member(chat_id, "me")
        except Exception:
            try:
                invite = await client.export_chat_invite_link(chat_id)
                await assistant.join_chat(invite)
            except Exception as join_err:
                logger.error("Could not get assistant into chat %s: %s", chat_id, join_err)
                return False, "Assistant cannot access this group. Add assistant account to group and retry."

        play_url = await _resolve_stream_url(stream_url, is_video=is_video)
        if not play_url:
            return False, "Unable to resolve playable stream URL."

        gc = call_manager.get(chat_id)

        if not call_manager.is_connected(chat_id):
            await gc.join_group_call(chat_id, play_url, is_video=is_video)
            await asyncio.sleep(1)
        else:
            await gc.change_stream(chat_id, play_url, is_video=is_video)

        logger.info("Started stream in chat %s (is_video=%s)", chat_id, is_video)
        return True, ""
    except Exception as e:
        err = str(e)
        low = err.lower()
        if "groupcall" in low and ("invalid" in low or "forbidden" in low or "not" in low):
            msg = "No active voice chat. Start voice chat in group first."
        elif "chat admin required" in low or "right" in low:
            msg = "Bot lacks required admin rights for voice chat."
        elif "peer id invalid" in low or "peer_id_invalid" in low:
            msg = "Assistant is not in this group."
        else:
            msg = err[:180]

        logger.error("Stream error in %s: %s", chat_id, e, exc_info=True)
        return False, msg


def _safe(text: str) -> str:
    return text.replace("*", "").replace("_", "").replace("[", "").replace("]", "").replace("`", "")


@Client.on_message(filters.command(["play", "playforce", "vplay", "vplayforce"]) & filters.group)
@error_handler
@rate_limit(5)
async def play_command(client: Client, message: Message):
    if getattr(message, "edit_date", None):
        return
    if _is_duplicate_play(message.chat.id, message.id):
        return

    cmd = message.command[0].lower()
    is_force = "force" in cmd
    is_video = cmd.startswith("v")

    if is_force and not await is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("Admins only.", quote=True)

    # Incident drain mode: block new play requests for non-sudo users.
    try:
        drain_mode = bool(await get_dynamic_config("drain_mode", default=False))
    except Exception:
        drain_mode = False
    if drain_mode and message.from_user.id not in SUDO_USERS:
        return await message.reply_text("Playback requests are temporarily paused (drain mode).", quote=True)

    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply_text(f"Usage: `/{cmd} [name or URL]`", quote=True)

    query = " ".join(message.command[1:])
    status_msg = await message.reply_text("Searching...", quote=True)

    info = await _extract_info(query, video=is_video)
    if not info:
        return await status_msg.edit_text("Media not found.")

    settings = await fetch_settings(message.chat.id)
    max_duration = int(settings.get("max_duration", MAX_DURATION))
    queue_cap = int(settings.get("queue_cap", 50))

    if info["duration"] > max_duration:
        return await status_msg.edit_text(f"Too long (max {max_duration // 60}m).")

    if queue_size(message.chat.id) >= queue_cap and message.from_user.id not in SUDO_USERS:
        return await status_msg.edit_text(f"Queue is full (cap {queue_cap}).")

    if has_duplicate(message.chat.id, info.get("url", ""), info.get("title", "")) and message.from_user.id not in SUDO_USERS:
        return await status_msg.edit_text("This track is already in queue.")

    title = _safe(info["title"])
    track = {
        "title": info["title"],
        "url": info["url"],
        "duration": info["duration"],
        "requested_by": message.from_user.id,
        "is_video": is_video,
    }

    position = add_to_queue(message.chat.id, track, force=is_force)

    if position == 0:
        duration_str = f"{track['duration'] // 60:02d}:{track['duration'] % 60:02d}" if track["duration"] else "Live"
        ui_text = (
            f"**AURALYX PLAYER • {'VIDEO' if is_video else 'AUDIO'}**\n"
            f"`---------------------------`\n"
            f"Track: `{title[:38]}`\n"
            f"Duration: `{duration_str}`\n"
            f"Mode: `{'Force' if is_force else 'Queue'}`\n"
            f"`---------------------------`"
        )

        buttons = [[
            InlineKeyboardButton("Pause", callback_data="pause"),
            InlineKeyboardButton("Next", callback_data="next"),
            InlineKeyboardButton("Stop", callback_data="stop"),
            InlineKeyboardButton("Queue", callback_data="queue"),
        ]]

        sent_main = False
        if info.get("thumbnail"):
            try:
                await message.reply_photo(
                    photo=info["thumbnail"],
                    caption=ui_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    quote=True,
                )
                await status_msg.delete()
                sent_main = True
            except Exception as e:
                logger.warning("Thumbnail send failed: %s", e)

        if not sent_main:
            await status_msg.edit_text(ui_text, reply_markup=InlineKeyboardMarkup(buttons))

        ok, err = await _start_stream(client, message.chat.id, info["url"], is_video=is_video)
        if not ok:
            return await message.reply_text(f"Stream failed: `{_safe(err) or 'unknown error'}`", quote=True)

        await increment_stat("total_plays")
        await record_track_play(message.chat.id, track)
    else:
        await status_msg.edit_text(
            f"**QUEUED**\n"
            f"`---------------------------`\n"
            f"Position: `#{position + 1}`\n"
            f"Track: `{title[:38]}`\n"
            f"`---------------------------`"
        )


@Client.on_message(filters.command(["search", "vsearch"]) & filters.group)
@error_handler
@rate_limit(5)
async def search_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/search <query>`", quote=True)

    query = " ".join(message.command[1:])
    is_video = message.command[0].lower() == "vsearch"
    status = await message.reply_text("Searching top results...", quote=True)

    try:
        import yt_dlp

        def run_search() -> list[dict]:
            opts = {
                "format": "best[height<=360][vcodec!=none][acodec!=none]/best" if is_video else "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                rows = []
                for entry in (info.get("entries") or [])[:5]:
                    rows.append(
                        {
                            "title": entry.get("title", "Unknown"),
                            "url": entry.get("url"),
                            "duration": int(entry.get("duration", 0) or 0),
                            "is_video": is_video,
                        }
                    )
                return rows

        results = await asyncio.to_thread(run_search)
        if not results:
            return await status.edit_text("No results found.")

        _search_cache[(message.chat.id, message.from_user.id)] = (time.monotonic(), results)

        lines = ["Search Results:"]
        buttons = []
        for i, row in enumerate(results, start=1):
            dur = row.get("duration", 0)
            dur_s = f"{dur // 60:02d}:{dur % 60:02d}" if dur else "Live"
            lines.append(f"{i}. `{row.get('title', 'Unknown')[:42]}` ({dur_s})")
            buttons.append([InlineKeyboardButton(f"Add #{i}", callback_data=f"search_add:{i}")])

        await status.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        await status.edit_text(f"Search failed: `{e}`")


@Client.on_callback_query(filters.regex(r"^search_add:(\d+)$"))
async def search_add_callback(client: Client, callback: CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    key = (chat_id, user_id)
    payload = _search_cache.get(key)
    if not payload:
        return await callback.answer("Search expired. Run /search again.", show_alert=True)

    ts, results = payload
    if time.monotonic() - ts > 180:
        _search_cache.pop(key, None)
        return await callback.answer("Search expired. Run /search again.", show_alert=True)

    try:
        idx = int(callback.data.split(":", 1)[1]) - 1
    except Exception:
        return await callback.answer("Invalid result.", show_alert=True)

    if idx < 0 or idx >= len(results):
        return await callback.answer("Invalid result index.", show_alert=True)

    track = dict(results[idx])
    track["requested_by"] = user_id

    settings = await fetch_settings(chat_id)
    queue_cap = int(settings.get("queue_cap", 50))
    if queue_size(chat_id) >= queue_cap and user_id not in SUDO_USERS:
        return await callback.answer(f"Queue full (cap {queue_cap}).", show_alert=True)

    if has_duplicate(chat_id, track.get("url", ""), track.get("title", "")) and user_id not in SUDO_USERS:
        return await callback.answer("Track already in queue.", show_alert=True)

    pos = add_to_queue(chat_id, track)
    if pos == 0:
        ok, err = await _start_stream(client, chat_id, track["url"], is_video=bool(track.get("is_video", False)))
        if not ok:
            return await callback.answer(f"Failed: {(_safe(err) or 'unknown')[:60]}", show_alert=True)
        await increment_stat("total_plays")
        await record_track_play(chat_id, track)
        await callback.answer("Now playing.", show_alert=False)
    else:
        await callback.answer(f"Queued at #{pos + 1}", show_alert=False)

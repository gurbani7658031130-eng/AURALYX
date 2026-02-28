"""
Auralyx Music - Music Controls
"""

import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.call import call_manager
from core.permissions import admin_only, is_admin
from core.voice_cleanup import record_activity, remove_chat
from database.mongo import record_track_play
from utils.decorators import error_handler
from utils.music_settings import fetch_settings
from utils.queue import (
    add_to_queue,
    append_track,
    clear_queue,
    current_track,
    get_queue,
    pop_queue,
    prepend_track,
)
from utils.stream import kill_stream

logger = logging.getLogger(__name__)

_vote_skips: dict[int, set[int]] = {}
_idle_tasks: dict[int, asyncio.Task] = {}


def _reset_votes(chat_id: int):
    _vote_skips.pop(chat_id, None)


async def _extract_autoplay_track(seed_title: str, as_video: bool = False) -> dict | None:
    """Fetch one related track for autoplay using yt-dlp search."""
    if not seed_title:
        return None
    try:
        import yt_dlp

        def run_search():
            opts = {
                "format": "best[height<=360][vcodec!=none][acodec!=none]/best" if as_video else "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "default_search": "ytsearch",
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{seed_title} related", download=False)
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                return {
                    "title": info.get("title", "Autoplay"),
                    "url": info.get("url"),
                    "duration": int(info.get("duration", 0) or 0),
                    "requested_by": 0,
                    "is_video": as_video,
                }

        return await asyncio.to_thread(run_search)
    except Exception as e:
        logger.warning("Autoplay extraction failed: %s", e)
        return None


async def _auto_leave_task(client: Client, chat_id: int):
    settings = await fetch_settings(chat_id)
    idle_timeout = 600
    try:
        await asyncio.sleep(idle_timeout)
        if not get_queue(chat_id):
            gc = call_manager.get(chat_id)
            try:
                gc.stop_playout()
                await gc.leave_current_group_call()
            except Exception as e:
                logger.debug("Auto-leave leave_current_group_call failed in %s: %s", chat_id, e)
            await kill_stream(chat_id)
            clear_queue(chat_id)
            _reset_votes(chat_id)
            call_manager.remove(chat_id)
            logger.info("Auto-left idle VC in %s", chat_id)
    except asyncio.CancelledError:
        return


def start_idle_timer(client: Client, chat_id: int):
    cancel_idle_timer(chat_id)
    _idle_tasks[chat_id] = asyncio.create_task(_auto_leave_task(client, chat_id))


def cancel_idle_timer(chat_id: int):
    task = _idle_tasks.pop(chat_id, None)
    if task:
        task.cancel()


async def _do_skip(client: Client, chat_id: int, message: Message):
    from .player import _safe, _start_stream

    _reset_votes(chat_id)
    settings = await fetch_settings(chat_id)
    loop_mode = settings.get("loop_mode", "off")
    autoplay = bool(settings.get("autoplay", False))

    current = pop_queue(chat_id)

    # Queue-loop puts skipped current track at the tail.
    if current and loop_mode == "queue":
        append_track(chat_id, current)

    # Track-loop replays the same track if queue became empty.
    if current and loop_mode == "track" and not get_queue(chat_id):
        prepend_track(chat_id, current)

    # Autoplay fallback when queue is empty.
    if current and autoplay and not get_queue(chat_id):
        auto = await _extract_autoplay_track(current.get("title", ""), as_video=bool(current.get("is_video", False)))
        if auto and auto.get("url"):
            add_to_queue(chat_id, auto)

    next_track = current_track(chat_id)
    if not next_track:
        gc = call_manager.get(chat_id)
        try:
            gc.stop_playout()
            await gc.leave_current_group_call()
        except Exception as e:
            logger.debug("Skip cleanup leave failed in %s: %s", chat_id, e)
        await kill_stream(chat_id)
        clear_queue(chat_id)
        call_manager.remove(chat_id)
        await message.reply_text("Skipped. Queue empty.", quote=True)
        start_idle_timer(client, chat_id)
        return

    ok = await _start_stream(
        client,
        chat_id,
        next_track.get("url", ""),
        is_video=bool(next_track.get("is_video", False)),
    )
    if not ok:
        return await message.reply_text("Failed to load next track.", quote=True)

    await record_track_play(chat_id, next_track)
    await message.reply_text(f"Skipped. Next: `{_safe(next_track.get('title', 'Unknown'))[:40]}`", quote=True)
    cancel_idle_timer(chat_id)
    record_activity(chat_id)


@Client.on_message(filters.command("skip") & filters.group)
@error_handler
async def skip_command(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if await is_admin(client, chat_id, user_id):
        await _do_skip(client, chat_id, message)
        return

    settings = await fetch_settings(chat_id)
    threshold = int(settings.get("vote_skip_threshold", 3))

    if chat_id not in _vote_skips:
        _vote_skips[chat_id] = set()
    _vote_skips[chat_id].add(user_id)

    count = len(_vote_skips[chat_id])
    if count >= threshold:
        await _do_skip(client, chat_id, message)
    else:
        await message.reply_text(f"Vote skip: {count}/{threshold}. Need {threshold - count} more.", quote=True)


@Client.on_message(filters.command("stop") & filters.group)
@error_handler
async def stop_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    chat_id = message.chat.id
    clear_queue(chat_id)
    _reset_votes(chat_id)
    cancel_idle_timer(chat_id)
    await kill_stream(chat_id)
    remove_chat(chat_id)

    gc = call_manager.get(chat_id)
    try:
        gc.stop_playout()
        await gc.leave_current_group_call()
    except Exception as e:
        logger.debug("Stop leave failed in %s: %s", chat_id, e)

    call_manager.remove(chat_id)
    await message.reply_text("Stopped and cleared.", quote=True)


@Client.on_message(filters.command("pause") & filters.group)
@error_handler
async def pause_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    gc = call_manager.get(message.chat.id)
    try:
        gc.pause_playout()
    except Exception as e:
        logger.debug("Pause failed in %s: %s", message.chat.id, e)
    await message.reply_text("Paused.", quote=True)


@Client.on_message(filters.command("resume") & filters.group)
@error_handler
async def resume_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    gc = call_manager.get(message.chat.id)
    try:
        gc.resume_playout()
    except Exception as e:
        logger.debug("Resume failed in %s: %s", message.chat.id, e)
    await message.reply_text("Resumed.", quote=True)


@Client.on_message(filters.command(["nowplaying", "current"]) & filters.group)
@error_handler
async def nowplaying_command(client: Client, message: Message):
    track = current_track(message.chat.id)
    if not track:
        return await message.reply_text("Nothing is playing right now.", quote=True)

    title = track.get("title", "Unknown")[:40]
    duration = track.get("duration", 0)
    dur_str = f"{duration // 60:02d}:{duration % 60:02d}" if duration else "Live"

    await message.reply_text(
        f"**NOW PLAYING**\n"
        f"`---------------------------`\n"
        f"Track: `{title}`\n"
        f"Duration: `{dur_str}`\n"
        f"`---------------------------`",
        quote=True,
    )


@Client.on_message(filters.command("queue") & filters.group)
@error_handler
async def queue_command(client: Client, message: Message):
    queue = get_queue(message.chat.id)
    if not queue:
        return await message.reply_text("Queue is empty.", quote=True)

    text = "**PLAYBACK QUEUE**\n`---------------------------`\n"
    for i, track in enumerate(queue[:10]):
        prefix = "NOW" if i == 0 else f"{i + 1}."
        text += f"{prefix} `{track['title'][:35]}`\n"
    if len(queue) > 10:
        text += f"\n+{len(queue)-10} more queued"
    text += "\n`---------------------------`"

    buttons = [[
        InlineKeyboardButton("Pause", callback_data="pause"),
        InlineKeyboardButton("Next", callback_data="next"),
        InlineKeyboardButton("Stop", callback_data="stop"),
    ]]
    await message.reply_text(text, quote=True, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex("^(pause|next|stop|queue)$"))
async def cb_handler(client: Client, callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if not await is_admin(client, chat_id, callback.from_user.id):
        return await callback.answer("Admins only.", show_alert=True)

    data = callback.data
    gc = call_manager.get(chat_id)

    if data == "pause":
        try:
            gc.pause_playout()
            await callback.answer("Paused")
        except Exception:
            await callback.answer("Error")
    elif data == "next":
        await _do_skip(client, chat_id, callback.message)
        await callback.answer("Skipped")
    elif data == "stop":
        clear_queue(chat_id)
        _reset_votes(chat_id)
        cancel_idle_timer(chat_id)
        await kill_stream(chat_id)
        remove_chat(chat_id)
        try:
            gc.stop_playout()
            await gc.leave_current_group_call()
        except Exception:
            pass
        call_manager.remove(chat_id)
        await callback.answer("Stopped")
        try:
            await callback.message.delete()
        except Exception:
            pass
    elif data == "queue":
        await callback.answer()
        message = callback.message
        message.from_user = callback.from_user
        await queue_command(client, message)

"""
Auralyx Music - Music Advanced Controls
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from core.permissions import admin_only
from database.mongo import get_chat_history, get_chat_top_tracks
from utils.decorators import error_handler, rate_limit
from utils.music_settings import fetch_settings, set_setting
from utils.queue import (
    clear_queue,
    current_track,
    get_queue,
    remove_position,
    shuffle_queue,
)

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("autoplay") & filters.group)
@error_handler
async def autoplay_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    if len(message.command) < 2 or message.command[1].lower() not in {"on", "off"}:
        return await message.reply_text("Usage: `/autoplay on|off`", quote=True)

    enabled = message.command[1].lower() == "on"
    await set_setting(message.chat.id, "autoplay", enabled)
    await message.reply_text(f"Autoplay {'enabled' if enabled else 'disabled'}.", quote=True)


@Client.on_message(filters.command("loop") & filters.group)
@error_handler
async def loop_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    if len(message.command) < 2 or message.command[1].lower() not in {"off", "track", "queue"}:
        return await message.reply_text("Usage: `/loop off|track|queue`", quote=True)

    mode = message.command[1].lower()
    await set_setting(message.chat.id, "loop_mode", mode)
    await message.reply_text(f"Loop mode set to `{mode}`.", quote=True)


@Client.on_message(filters.command("shuffle") & filters.group)
@error_handler
async def shuffle_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    count = shuffle_queue(message.chat.id)
    if count == 0:
        return await message.reply_text("Queue is too short to shuffle.", quote=True)
    await message.reply_text(f"Queue shuffled ({count} tracks).", quote=True)


@Client.on_message(filters.command("remove") & filters.group)
@error_handler
async def remove_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply_text("Usage: `/remove <position>`", quote=True)

    pos = int(message.command[1])
    removed = remove_position(message.chat.id, pos)
    if not removed:
        return await message.reply_text("Invalid position. You cannot remove #1 (currently playing).", quote=True)
    await message.reply_text(f"Removed `{removed.get('title', 'Unknown')[:40]}` from queue.", quote=True)


@Client.on_message(filters.command("clear") & filters.group)
@error_handler
async def clear_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    q = get_queue(message.chat.id)
    if len(q) <= 1:
        return await message.reply_text("No pending tracks to clear.", quote=True)

    from utils.queue import _queues
    from collections import deque

    _queues[message.chat.id] = deque([q[0]])
    await message.reply_text("Cleared queued tracks. Current song continues.", quote=True)


@Client.on_message(filters.command("replay") & filters.group)
@error_handler
async def replay_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    track = current_track(message.chat.id)
    if not track:
        return await message.reply_text("Nothing is playing.", quote=True)

    from .player import _start_stream

    ok = await _start_stream(
        client,
        message.chat.id,
        track.get("url", ""),
        is_video=bool(track.get("is_video", False)),
    )
    if not ok:
        return await message.reply_text("Failed to replay current track.", quote=True)
    await message.reply_text("Replaying current track from start.", quote=True)


@Client.on_message(filters.command("settings") & filters.group)
@error_handler
async def settings_command(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        return await message.reply_text("Usage: `/settings music`", quote=True)

    if args[0].lower() != "music":
        return await message.reply_text("Only `music` settings are supported.", quote=True)

    # View mode
    if len(args) == 1:
        s = await fetch_settings(message.chat.id)
        text = (
            "Music Settings\n"
            f"autoplay: `{s.get('autoplay')}`\n"
            f"loop_mode: `{s.get('loop_mode')}`\n"
            f"queue_cap: `{s.get('queue_cap')}`\n"
            f"vote_skip_threshold: `{s.get('vote_skip_threshold')}`\n"
            f"max_duration: `{s.get('max_duration')}`\n"
            f"default_volume: `{s.get('default_volume')}`\n\n"
            "Set examples:\n"
            "`/settings music queue_cap 80`\n"
            "`/settings music vote_skip_threshold 4`\n"
            "`/settings music max_duration 5400`"
        )
        return await message.reply_text(text, quote=True)

    # Update mode
    if not await admin_only(client, message):
        return

    if len(args) < 3:
        return await message.reply_text("Usage: `/settings music <key> <value>`", quote=True)

    key = args[1].lower()
    value_raw = args[2].lower()

    if key in {"queue_cap", "vote_skip_threshold", "max_duration", "default_volume"}:
        if not value_raw.isdigit():
            return await message.reply_text("Value must be an integer.", quote=True)
        value = int(value_raw)

        if key == "queue_cap":
            value = max(10, min(value, 200))
        elif key == "vote_skip_threshold":
            value = max(2, min(value, 10))
        elif key == "max_duration":
            value = max(60, min(value, 10800))
        elif key == "default_volume":
            value = max(1, min(value, 200))

        await set_setting(message.chat.id, key, value)
        return await message.reply_text(f"Updated `{key}` to `{value}`.", quote=True)

    if key in {"autoplay"}:
        if value_raw not in {"on", "off", "true", "false"}:
            return await message.reply_text("Use on/off.", quote=True)
        value = value_raw in {"on", "true"}
        await set_setting(message.chat.id, key, value)
        return await message.reply_text(f"Updated `{key}` to `{value}`.", quote=True)

    if key == "loop_mode":
        if value_raw not in {"off", "track", "queue"}:
            return await message.reply_text("Use one of: off, track, queue.", quote=True)
        await set_setting(message.chat.id, key, value_raw)
        return await message.reply_text(f"Updated `{key}` to `{value_raw}`.", quote=True)

    await message.reply_text("Unknown music setting key.", quote=True)


@Client.on_message(filters.command("history") & filters.group)
@error_handler
@rate_limit(3)
async def history_command(client: Client, message: Message):
    rows = await get_chat_history(message.chat.id, limit=10)
    if not rows:
        return await message.reply_text("No play history yet.", quote=True)

    lines = ["Recent Tracks:"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. `{row.get('title', 'Unknown')[:45]}`")
    await message.reply_text("\n".join(lines), quote=True)


@Client.on_message(filters.command("toptracks") & filters.group)
@error_handler
@rate_limit(3)
async def toptracks_command(client: Client, message: Message):
    rows = await get_chat_top_tracks(message.chat.id, limit=10)
    if not rows:
        return await message.reply_text("No top tracks yet.", quote=True)

    lines = ["Top Tracks:"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. `{row.get('title', 'Unknown')[:42]}` - `{row.get('count', 0)}x`")
    await message.reply_text("\n".join(lines), quote=True)


@Client.on_message(filters.command("seek") & filters.group)
@error_handler
async def seek_command(client: Client, message: Message):
    if not await admin_only(client, message):
        return

    await message.reply_text(
        "Seek is not supported with the current streaming backend. "
        "It requires FFmpeg restart with time offset.",
        quote=True,
    )


@Client.on_message(filters.command("lyrics") & filters.group)
@error_handler
@rate_limit(10)
async def lyrics_command(client: Client, message: Message):
    if len(message.command) < 2:
        track = current_track(message.chat.id)
        if track:
            query = track.get("title", "")
        else:
            await message.reply_text("Usage: `/lyrics <song name>`", quote=True)
            return
    else:
        query = " ".join(message.command[1:])

    if not query:
        await message.reply_text("Provide a song name.", quote=True)
        return

    msg = await message.reply_text(f"Searching lyrics for **{query}**...", quote=True)

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://some-random-api.com/lyrics?title={query}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    await msg.edit_text("Lyrics not found.")
                    return
                data = await resp.json()

        title = data.get("title", query)
        author = data.get("author", "Unknown")
        lyrics = data.get("lyrics", "")

        if not lyrics:
            await msg.edit_text("No lyrics found for that song.")
            return

        if len(lyrics) > 3500:
            lyrics = lyrics[:3500] + "\n\n... _truncated_"

        await msg.edit_text(
            f"{title} - _{author}_\n"
            "--------------------\n"
            f"{lyrics}"
        )
    except ImportError:
        await msg.edit_text("`aiohttp` not installed. Run `pip install aiohttp`.")
    except Exception as e:
        await msg.edit_text(f"Failed to fetch lyrics: `{e}`")

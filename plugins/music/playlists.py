"""Playlist commands for music module."""

from pyrogram import Client, filters
from pyrogram.types import Message

from core.permissions import admin_only
from database.mongo import (
    delete_chat_playlist,
    get_chat_playlist,
    list_chat_playlists,
    save_chat_playlist,
)
from utils.decorators import error_handler, rate_limit
from utils.queue import add_to_queue, current_track, get_queue


@Client.on_message(filters.command("playlist") & filters.group)
@error_handler
@rate_limit(3)
async def playlist_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "Usage:\n"
            "`/playlist save <name>`\n"
            "`/playlist play <name>`\n"
            "`/playlist list`\n"
            "`/playlist delete <name>`",
            quote=True,
        )

    action = message.command[1].lower()
    chat_id = message.chat.id

    if action == "save":
        if not await admin_only(client, message):
            return
        if len(message.command) < 3:
            return await message.reply_text("Usage: `/playlist save <name>`", quote=True)

        name = " ".join(message.command[2:]).strip().lower()[:32]
        q = get_queue(chat_id)
        if not q:
            return await message.reply_text("Queue is empty.", quote=True)

        tracks = []
        for row in q[:100]:
            tracks.append(
                {
                    "title": row.get("title", "Unknown")[:128],
                    "url": row.get("url", ""),
                    "duration": int(row.get("duration", 0) or 0),
                    "is_video": bool(row.get("is_video", False)),
                }
            )

        await save_chat_playlist(chat_id, name, tracks, message.from_user.id)
        return await message.reply_text(f"Saved playlist `{name}` with {len(tracks)} tracks.", quote=True)

    if action == "list":
        rows = await list_chat_playlists(chat_id, limit=20)
        if not rows:
            return await message.reply_text("No playlists saved in this chat.", quote=True)

        lines = ["Playlists:"]
        for i, row in enumerate(rows, start=1):
            lines.append(f"{i}. `{row.get('name', 'unknown')}` ({len(row.get('tracks', []))} tracks)")
        return await message.reply_text("\n".join(lines), quote=True)

    if action == "delete":
        if not await admin_only(client, message):
            return
        if len(message.command) < 3:
            return await message.reply_text("Usage: `/playlist delete <name>`", quote=True)

        name = " ".join(message.command[2:]).strip().lower()[:32]
        ok = await delete_chat_playlist(chat_id, name)
        if not ok:
            return await message.reply_text("Playlist not found.", quote=True)
        return await message.reply_text(f"Deleted playlist `{name}`.", quote=True)

    if action == "play":
        if len(message.command) < 3:
            return await message.reply_text("Usage: `/playlist play <name>`", quote=True)

        name = " ".join(message.command[2:]).strip().lower()[:32]
        doc = await get_chat_playlist(chat_id, name)
        if not doc:
            return await message.reply_text("Playlist not found.", quote=True)

        tracks = doc.get("tracks", [])[:100]
        if not tracks:
            return await message.reply_text("Playlist is empty.", quote=True)

        was_empty = current_track(chat_id) is None
        for row in tracks:
            add_to_queue(
                chat_id,
                {
                    "title": row.get("title", "Unknown"),
                    "url": row.get("url", ""),
                    "duration": int(row.get("duration", 0) or 0),
                    "requested_by": message.from_user.id,
                    "is_video": bool(row.get("is_video", False)),
                },
            )

        if was_empty:
            from .player import _start_stream

            first = current_track(chat_id)
            if first and first.get("url"):
                ok = await _start_stream(client, chat_id, first["url"], is_video=bool(first.get("is_video", False)))
                if not ok:
                    return await message.reply_text("Added playlist but failed to start stream.", quote=True)

        return await message.reply_text(f"Loaded playlist `{name}` ({len(tracks)} tracks).", quote=True)

    await message.reply_text("Unknown action. Use save/play/list/delete.", quote=True)

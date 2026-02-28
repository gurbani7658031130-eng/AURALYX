"""
Auralyx Music — Admin: Moderation
/mute, /unmute, /ban, /unban, /kick, /pin, /unpin, /purge

All commands support TWO targeting modes:
  1. Reply to a user's message
  2. Provide user ID as argument: /ban 123456789 reason

Owner/Sudo restriction is enforced by admin_only() in permissions.py.
"""

import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from core.permissions import admin_only
from utils.decorators import error_handler, permission_required
from utils.reactions import send_reaction

logger = logging.getLogger(__name__)


async def _resolve_target(client: Client, message: Message):
    """
    Resolve the target user from either:
      1. Reply to a message (takes priority)
      2. First argument as user ID or @username
    
    Returns:
        (user_id, display_name, reason) or (None, None, None) if no target found.
    """
    # Method 1: Reply
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        reason = " ".join(message.command[1:]) or "No reason"
        return target.id, target.mention, reason

    # Method 2: User ID or @username as first argument
    if len(message.command) >= 2:
        identifier = message.command[1]
        reason = " ".join(message.command[2:]) or "No reason"

        # Try as numeric ID
        try:
            user_id = int(identifier)
            # Try to fetch display name
            try:
                user = await client.get_users(user_id)
                return user_id, user.mention, reason
            except Exception:
                return user_id, f"`{user_id}`", reason
        except ValueError:
            pass

        # Try as @username
        if identifier.startswith("@"):
            try:
                user = await client.get_users(identifier)
                return user.id, user.mention, reason
            except Exception:
                await message.reply_text(f"• User `{identifier}` not found.", quote=True)
                return None, None, None

    return None, None, None


@Client.on_message(filters.command("mute") & filters.group)
@error_handler
@permission_required("mute")
async def mute_command(client: Client, message: Message):
    """Mute a user. Usage: reply or /mute <user_id|@username> [reason]"""
    user_id, name, reason = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/mute <user_id> [reason]`", quote=True)
        return

    try:
        await client.restrict_chat_member(
            message.chat.id, user_id,
            permissions=ChatPermissions()
        )
        await message.reply_text(
            f"🔇 **Muted** {name}\n• Reason: _{reason}_",
            quote=True,
        )
        await send_reaction(client, message, "admin_action")
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("unmute") & filters.group)
@error_handler
@permission_required("unmute")
async def unmute_command(client: Client, message: Message):
    """Unmute a user. Usage: reply or /unmute <user_id|@username>"""
    user_id, name, _ = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/unmute <user_id>`", quote=True)
        return

    try:
        await client.restrict_chat_member(
            message.chat.id, user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        )
        await message.reply_text(f"🔊 **Unmuted** {name}", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("ban") & filters.group)
@error_handler
@permission_required("ban")
async def ban_command(client: Client, message: Message):
    """Ban a user. Usage: reply or /ban <user_id|@username> [reason]"""
    user_id, name, reason = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/ban <user_id> [reason]`", quote=True)
        return

    try:
        await client.ban_chat_member(message.chat.id, user_id)
        await message.reply_text(
            f"🔨 **Banned** {name}\n• Reason: _{reason}_",
            quote=True,
        )
        await send_reaction(client, message, "admin_action")
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("unban") & filters.group)
@error_handler
async def unban_command(client: Client, message: Message):
    """Unban a user. Usage: reply or /unban <user_id|@username>"""
    if not await admin_only(client, message):
        return

    user_id, name, _ = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/unban <user_id>`", quote=True)
        return

    try:
        await client.unban_chat_member(message.chat.id, user_id)
        await message.reply_text(f"✅ **Unbanned** {name}", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("kick") & filters.group)
@error_handler
async def kick_command(client: Client, message: Message):
    """Kick a user (they can rejoin). Usage: reply or /kick <user_id|@username>"""
    if not await admin_only(client, message):
        return

    user_id, name, _ = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/kick <user_id>`", quote=True)
        return

    try:
        await client.ban_chat_member(message.chat.id, user_id)
        await asyncio.sleep(1)
        await client.unban_chat_member(message.chat.id, user_id)
        await message.reply_text(f"👢 **Kicked** {name}", quote=True)
        await send_reaction(client, message, "admin_action")
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("pin") & filters.group)
@error_handler
async def pin_command(client: Client, message: Message):
    """Pin a message (reply only)."""
    if not await admin_only(client, message):
        return

    if not message.reply_to_message:
        await message.reply_text("• Reply to a message to pin.", quote=True)
        return

    try:
        await message.reply_to_message.pin()
        loud = "loud" in message.text.lower()
        if not loud:
            await message.reply_text("📌 **Message pinned.**", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("unpin") & filters.group)
@error_handler
async def unpin_command(client: Client, message: Message):
    """Unpin the replied message or all pinned messages."""
    if not await admin_only(client, message):
        return

    try:
        if message.reply_to_message:
            await message.reply_to_message.unpin()
            await message.reply_text("📌 **Message unpinned.**", quote=True)
        else:
            await client.unpin_all_chat_messages(message.chat.id)
            await message.reply_text("📌 **All messages unpinned.**", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("purge") & filters.group)
@error_handler
async def purge_command(client: Client, message: Message):
    """Delete the last N messages. Usage: /purge <count> or reply + /purge"""
    if not await admin_only(client, message):
        return

    if message.reply_to_message:
        # Delete from replied message to current
        chat_id = message.chat.id
        start_id = message.reply_to_message.id
        end_id = message.id
        msg_ids = list(range(start_id, end_id + 1))
        # Telegram allows max 100 per batch
        for i in range(0, len(msg_ids), 100):
            batch = msg_ids[i:i+100]
            try:
                await client.delete_messages(chat_id, batch)
            except Exception:
                pass
        return

    # Delete last N messages
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/purge <count>` (max 100)", quote=True)
        return

    try:
        count = min(int(message.command[1]), 100)
    except ValueError:
        await message.reply_text("• Count must be a number.", quote=True)
        return

    chat_id = message.chat.id
    deleted = 0
    async for msg in client.get_chat_history(chat_id, limit=count + 1):
        try:
            await msg.delete()
            deleted += 1
        except Exception:
            pass

    notify = await message.reply_text(f"🗑️ **Purged {deleted} messages.**")
    await asyncio.sleep(3)
    try:
        await notify.delete()
    except Exception:
        pass

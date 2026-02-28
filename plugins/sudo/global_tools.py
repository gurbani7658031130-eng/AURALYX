"""
Auralyx Music — Sudo: Global Tools
/gban, /ungban, /chatlist, /leave, /sysinfo, /log, /block, /unblock, /announce
"""

import os
import sys
import time
import logging
import platform
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, permission_required, sudo_only
from database.mongo import (
    gban_user, ungban_user, is_gbanned, get_gban_list,
    get_all_groups, get_total_users, get_total_groups,
)
from core.shadowban import shadow_ban, shadow_unban, is_shadowbanned
from utils.emojis import Emojis

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("gban"))
@error_handler
@sudo_only
async def gban_command(client: Client, message: Message):
    """Globally ban a user from all groups."""
    # Get target
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        reason = " ".join(message.command[1:]) or "No reason"
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
            reason = " ".join(message.command[2:]) or "No reason"
        except ValueError:
            await message.reply_text("• Invalid user ID.", quote=True)
            return
    else:
        await message.reply_text("• Reply to a user or provide ID. `/gban <id> [reason]`", quote=True)
        return

    if await is_gbanned(target_id):
        await message.reply_text("• User is already gbanned.", quote=True)
        return

    await gban_user(target_id, reason)
    await shadow_ban(target_id)  # Also shadowban for instant effect

    # Try to ban in all groups
    groups = await get_all_groups()
    banned = 0
    for chat_id in groups:
        try:
            await client.ban_chat_member(chat_id, target_id)
            banned += 1
        except Exception:
            pass

    await message.reply_text(
        f"🔨 **GLOBAL BAN**\n"
        f"━━━━━━━━━━━━━━\n"
        f"• User: `{target_id}`\n"
        f"• Reason: _{reason}_\n"
        f"• Banned in: **{banned}/{len(groups)}** groups",
        quote=True,
    )
    logger.warning("GBAN: user %s by sudo %s — %s", target_id, message.from_user.id, reason)


@Client.on_message(filters.command("ungban"))
@error_handler
@sudo_only
async def ungban_command(client: Client, message: Message):
    """Remove global ban."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("• Invalid user ID.", quote=True)
            return
    else:
        await message.reply_text("• Reply to a user or provide ID.", quote=True)
        return

    if not await is_gbanned(target_id):
        await message.reply_text("• User is not gbanned.", quote=True)
        return

    await ungban_user(target_id)
    await shadow_unban(target_id)

    # Try to unban in all groups  
    groups = await get_all_groups()
    unbanned = 0
    for chat_id in groups:
        try:
            await client.unban_chat_member(chat_id, target_id)
            unbanned += 1
        except Exception:
            pass

    await message.reply_text(
        f"✅ **UNGBANNED** `{target_id}`\n"
        f"• Unbanned in: **{unbanned}/{len(groups)}** groups",
        quote=True,
    )


@Client.on_message(filters.command("chatlist"))
@error_handler
@sudo_only
async def chatlist_command(client: Client, message: Message):
    """List all groups the bot is in."""
    groups = await get_all_groups()
    if not groups:
        await message.reply_text("• No groups registered.", quote=True)
        return

    text = f"📋 **Chat List** ({len(groups)} groups)\n━━━━━━━━━━━━━━\n"
    for i, chat_id in enumerate(groups[:30], 1):
        try:
            chat = await client.get_chat(chat_id)
            title = chat.title or "Unknown"
            members = chat.members_count or "?"
            text += f"  {i}. `{chat_id}` — **{title[:20]}** ({members} members)\n"
        except Exception:
            text += f"  {i}. `{chat_id}` — _Unavailable_\n"

    if len(groups) > 30:
        text += f"\n_... +{len(groups) - 30} more_"

    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("leave"))
@error_handler
@sudo_only
async def leave_command(client: Client, message: Message):
    """Make the bot leave a specific group."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/leave <chat_id>`", quote=True)
        return

    try:
        chat_id = int(message.command[1])
    except ValueError:
        await message.reply_text("• Invalid chat ID.", quote=True)
        return

    try:
        await client.leave_chat(chat_id)
        await message.reply_text(f"✅ Left group `{chat_id}`.", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("sysinfo"))
@error_handler
@permission_required("stats")
async def sysinfo_command(client: Client, message: Message):
    """Detailed system information."""
    import psutil
    from utils.resource_guard import get_resource_stats
    from utils.queue import active_queue_count

    res = get_resource_stats()
    uptime_sec = int(time.time() - psutil.boot_time())
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)

    disk = psutil.disk_usage("/") if os.name != "nt" else psutil.disk_usage("C:\\")

    await message.reply_text(
        f"🖥️ **SYSTEM INFO**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"**Runtime**\n"
        f"  Python: `{sys.version.split()[0]}`\n"
        f"  OS: `{platform.system()} {platform.release()}`\n"
        f"  Arch: `{platform.machine()}`\n"
        f"\n**Resources**\n"
        f"  CPU: `{res.get('cpu', 0)}%` ({psutil.cpu_count()} cores)\n"
        f"  RAM: `{res.get('ram_percent', 0)}%` ({res.get('ram_used_mb', 0)}MB/{res.get('ram_total_mb', 0)}MB)\n"
        f"  Disk: `{disk.percent}%` ({disk.used // (1024**3)}GB/{disk.total // (1024**3)}GB)\n"
        f"\n**Bot**\n"
        f"  Active Queues: `{active_queue_count()}`\n"
        f"  System Uptime: `{days}d {hours}h {mins}m`\n"
        f"━━━━━━━━━━━━━━━━━━",
        quote=True,
    )


@Client.on_message(filters.command("log"))
@error_handler
@permission_required("logs")
async def log_command(client: Client, message: Message):
    """Get last N lines from console (limited access)."""
    count = 30
    if len(message.command) >= 2:
        try:
            count = min(int(message.command[1]), 100)
        except ValueError:
            pass

    # Read from log file if exists, otherwise from stderr capture
    log_file = "auralyx.log"
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-count:]
        text = "".join(lines)
    else:
        text = "_No log file found._ Configure logging to a file for this command."

    if len(text) > 3800:
        text = text[-3800:]

    await message.reply_text(
        f"📄 **Last {count} log lines:**\n```\n{text}\n```",
        quote=True,
    )


@Client.on_message(filters.command("block"))
@error_handler
@sudo_only
async def block_command(client: Client, message: Message):
    """Hard block a user (they see 'you are blocked')."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("• Invalid user ID.", quote=True)
            return
    else:
        await message.reply_text("• Reply or provide user ID.", quote=True)
        return

    await shadow_ban(target_id)
    await message.reply_text(f"🚫 **Blocked** `{target_id}`.", quote=True)
    logger.info("BLOCK: user %s by sudo %s", target_id, message.from_user.id)


@Client.on_message(filters.command("unblock"))
@error_handler
@sudo_only
async def unblock_command(client: Client, message: Message):
    """Remove block from a user."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("• Invalid user ID.", quote=True)
            return
    else:
        await message.reply_text("• Reply or provide user ID.", quote=True)
        return

    await shadow_unban(target_id)
    await message.reply_text(f"✅ **Unblocked** `{target_id}`.", quote=True)


@Client.on_message(filters.command("announce"))
@error_handler
@sudo_only
async def announce_command(client: Client, message: Message):
    """Send a targeted announcement to a specific group."""
    if len(message.command) < 3:
        await message.reply_text("• Usage: `/announce <chat_id> <message>`", quote=True)
        return

    try:
        chat_id = int(message.command[1])
        text = " ".join(message.command[2:])
    except ValueError:
        await message.reply_text("• Invalid chat ID.", quote=True)
        return

    try:
        await client.send_message(
            chat_id,
            f"📢 **Announcement**\n━━━━━━━━━━━━━━\n{text}\n━━━━━━━━━━━━━━",
        )
        await message.reply_text(f"✅ Announcement sent to `{chat_id}`.", quote=True)
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)

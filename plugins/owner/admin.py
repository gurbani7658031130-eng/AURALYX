"""
Auralyx Music — Owner: Hidden Admin Tools
/o_stats, /o_forceleave, /o_restart, /o_maintenance
"""

import os
import sys

import psutil
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import owner_only, error_handler, owner_rate_limit
from core.maintenance import set_maintenance, is_maintenance
from utils.emojis import Emojis
from database.mongo import get_total_users, get_total_groups, db
from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("o_stats") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(3)
@error_handler
async def owner_stats(client: Client, message: Message):
    """Silent global stats for the owner."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"📊 **OWNER LOG**: `/o_stats` used by `{message.from_user.id}`")
        except: pass
    # System Stats
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    # DB Stats
    users = await get_total_users()
    groups = await get_total_groups()
    db_info = await db.command("dbstats")
    db_size = db_info.get("dataSize", 0) / (1024 * 1024) # MB
    
    # VC Stats
    from core.voice_cleanup import _activity
    active_vcs = len(_activity)
    
    text = (
        f"👑 **OWNER DASHBOARD**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 **System Health**\n"
        f"├ CPU: `[{cpu}%]`\n"
        f"├ RAM: `[{mem}%]`\n"
        f"└ DSK: `[{disk}%]`\n\n"
        f"📊 **Bot Metrics**\n"
        f"├ Users: `{users:,}`\n"
        f"├ Groups: `{groups:,}`\n"
        f"└ DB Size: `{db_size:.2f} MB`\n\n"
        f"🎵 **Active Streams**\n"
        f"└ Sessions: `{active_vcs}`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("o_forceleave") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_force_leave(client: Client, message: Message):
    """Owner override: disconnect ALL voice calls."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"🛑 **OWNER LOG**: `/o_forceleave` triggered by `{message.from_user.id}`")
        except: pass
    from core.call import call_manager
    from utils.queue import clear_queue
    from utils.stream import cleanup_all
    from core.voice_cleanup import _activity
    
    count = len(call_manager._calls)
    
    # Disconnect all active voice calls
    for cid in list(call_manager._calls):
        try:
            gc = call_manager._calls[cid]
            gc.stop_playout()
            await gc.leave_current_group_call()
        except Exception:
            pass
        clear_queue(cid)
        call_manager.remove(cid)
    
    await cleanup_all()
    _activity.clear()
    
    await message.reply_text(f"🛑 **Force Leave Executed.**\nCleared `{count}` active sessions.")


@Client.on_message(filters.command("o_maintenance") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_maintenance(client: Client, message: Message):
    """Silent maintenance toggle."""
    args = message.text.split()
    if len(args) < 2:
        st = "ON" if is_maintenance() else "OFF"
        await message.reply_text(f"🚧 **Maintenance: `{st}`**")
        return
        
    on = args[1].lower() == "on"
    await set_maintenance(on)
    await message.reply_text(f"🚧 **Maintenance set to {'ENABLED' if on else 'DISABLED'}.**")

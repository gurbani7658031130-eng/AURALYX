"""
Auralyx Music — Root System (Hidden)
Owner-only hidden root commands. Not listed in /help.
Works ONLY in private chat with the OWNER_ID.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Private filter: only OWNER in private DM
# ──────────────────────────────────────────────
_root_filter = filters.private & filters.user(OWNER_ID)


@Client.on_message(filters.command("root") & _root_filter)
async def root_activate(client: Client, message: Message):
    """
    Hidden root activation command.
    Only accessible by OWNER_ID in private chat.
    Not listed in any help menu.
    """
    logger.info("Root activated by OWNER (ID: %s)", message.from_user.id)
    await message.reply_text(
        "🔓 **Root Access Granted**\n\n"
        "Welcome back, Master.\n"
        "Use /rootpanel to manage the bot.\n\n"
        "⚠️ This panel is hidden and unavailable to other users.",
        quote=True,
    )


@Client.on_message(filters.command("rootpanel") & _root_filter)
async def root_panel(client: Client, message: Message):
    """Root management panel."""
    logger.info("Root panel accessed by OWNER (ID: %s)", message.from_user.id)
    await message.reply_text(
        "🛠 **Root Panel**\n\n"
        "Available commands:\n"
        "• `/rootstats` — Global statistics\n"
        "• `/o_stats` — System health\n"
        "• `/o_forceleave` — Disconnect all VCs\n"
        "• `/o_maintenance on/off` — Toggle maintenance\n"
        "• `/o_shadowban <id>` — Shadowban user\n"
        "• `/o_unshadow <id>` — Unshadowban user\n"
        "• `/o_give <id> <amount>` — Give coins\n"
        "• `/o_reset <id>` — Reset economy\n"
        "• `/o_eval <code>` — Execute Python\n"
        "• `/broadcast <msg>` — Broadcast to groups\n"
        "• `/restart` — Restart bot",
        quote=True,
    )


@Client.on_message(filters.command("rootstats") & _root_filter)
async def root_stats(client: Client, message: Message):
    """Global statistics for the owner — real data."""
    from database.mongo import get_total_users, get_total_groups, get_stat
    from utils.queue import active_queue_count
    from core.voice_cleanup import _activity
    from utils.resource_guard import get_resource_stats

    users = await get_total_users()
    groups = await get_total_groups()
    total_plays = await get_stat("total_plays")
    active_vcs = len(_activity)
    active_queues = active_queue_count()
    res = get_resource_stats()

    await message.reply_text(
        "📊 **Global Stats**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Groups served: `{groups:,}`\n"
        f"👤 Users registered: `{users:,}`\n"
        f"🎵 Total plays: `{total_plays:,}`\n"
        f"🎙️ Active VCs: `{active_vcs}`\n"
        f"📋 Active queues: `{active_queues}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⚡ CPU: `{res.get('cpu', 0)}%`\n"
        f"🧠 RAM: `{res.get('ram_percent', 0)}%` "
        f"({res.get('ram_used_mb', 0)} MB / {res.get('ram_total_mb', 0)} MB)",
        quote=True,
    )

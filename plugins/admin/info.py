"""
Auralyx Music — Admin: Info Commands
/stats and /ping.
"""

import logging
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler
from utils.resource_guard import get_resource_stats
from database.mongo import get_total_users, get_total_groups, get_stat

logger = logging.getLogger(__name__)

# Set at bot startup
_start_time = time.time()


def _format_uptime() -> str:
    """Return human-readable uptime."""
    delta = int(time.time() - _start_time)
    days, remainder = divmod(delta, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m {seconds}s"


@Client.on_message(filters.command("stats"))
@error_handler
async def stats_command(client: Client, message: Message):
    """Show bot statistics."""
    uptime = _format_uptime()
    res = get_resource_stats()
    total_users = await get_total_users()
    total_groups = await get_total_groups()
    total_plays = await get_stat("total_plays")

    await message.reply_text(
        "📊 **Auralyx Stats:**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ **Uptime:** `{uptime}`\n"
        f"👥 **Users:** `{total_users}`\n"
        f"💬 **Groups:** `{total_groups}`\n"
        f"🎵 **Total Plays:** `{total_plays}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• **CPU:** `{res['cpu']}%`\n"
        f"• **RAM:** `{res['ram_percent']}%` "
        f"({res['ram_used_mb']} MB / {res['ram_total_mb']} MB)",
        quote=True,
    )


@Client.on_message(filters.command("ping"))
@error_handler
async def ping_command(client: Client, message: Message):
    """Check bot latency."""
    start = time.perf_counter()
    msg = await message.reply_text("🏓 **Pinging...**", quote=True)
    end = time.perf_counter()
    latency = round((end - start) * 1000, 1)
    await msg.edit_text(f"🏓 **Pong!** `{latency}ms`")

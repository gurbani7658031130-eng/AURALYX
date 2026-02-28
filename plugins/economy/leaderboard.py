"""
Auralyx Music — Economy: Leaderboards
/toprich and /topkills commands.
Optimized for zero-lag text rendering.
"""

import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from database.mongo import get_top_users
from utils.emojis import Emojis
from core.leaderboard_cache import get_cached, set_cached
from core.vip import identity

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("toprich") & filters.group)
@error_handler
@rate_limit(5)
async def toprich_command(client: Client, message: Message):
    """Show top 10 richest users by wallet."""
    # Try cache first
    users = await get_cached("wallet", 10)
    if not users:
        users = await get_top_users("wallet", 10)
        if users:
            await set_cached("wallet", users)

    if not users:
        await message.reply_text(f"📊 **No economy data yet.**", quote=True)
        return

    text = f"🏆 **WEALTHY ELITE** 🏆\n━━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        user_id = u.get("user_id")
        orig_name = u.get("name", "Unknown")
        wallet = u.get("wallet", 0)
        
        display_name = await identity.get_name(user_id, orig_name, rank=i)
        
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        text += f"{medal} {display_name} — 💰 `{(wallet or 0):,}`\n"

    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("topkills") & filters.group)
@error_handler
@rate_limit(5)
async def topkills_command(client: Client, message: Message):
    """Show top 10 users by kills."""
    # Try cache first
    users = await get_cached("kills", 10)
    if not users:
        users = await get_top_users("kills", 10)
        if users:
            await set_cached("kills", users)

    if not users:
        await message.reply_text(f"📊 **No kill data yet.**", quote=True)
        return

    text = f"⚔️ **TOP KILLERS** ⚔️\n━━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        user_id = u.get("user_id")
        orig_name = u.get("name", "Unknown")
        kills = u.get("kills", 0)
        
        display_name = await identity.get_name(user_id, orig_name, rank=i)
        
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        text += f"{medal} {display_name} — ⚔️ `{(kills or 0)}`\n"

    await message.reply_text(text, quote=True)

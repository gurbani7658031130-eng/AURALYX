"""
Auralyx Music — Economy: Profile & Leaderboard
/profile — Full profile card, /leaderboard — Combined view
"""

import time
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from database.mongo import get_user_economy, ensure_user, get_top_users
from core.vip import identity
from core.leaderboard_cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_VIP_NAMES = {0: "None", 1: "🥈 Silver", 2: "🥇 Gold", 3: "💎 Platinum"}


@Client.on_message(filters.command("profile"))
@error_handler
@rate_limit(3)
async def profile_command(client: Client, message: Message):
    """Full profile card — shows everything about a user."""
    # Target: replied user or self
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    else:
        target = message.from_user

    target_id = target.id
    doc = await get_user_economy(target_id)
    name = target.first_name or "Unknown"

    wallet = doc.get("wallet", 0)
    bank = doc.get("bank", 0)
    net_worth = wallet + bank
    kills = doc.get("kills", 0)
    deaths = doc.get("deaths", 0)
    kd = f"{kills / deaths:.1f}" if deaths > 0 else str(kills)
    level = doc.get("level", 1)
    xp = doc.get("xp", 0)
    needed = level * 500
    xp_bar = _xp_progress_bar(xp, needed)
    streak = doc.get("streak", 0)
    vip_level = doc.get("vip_level", 0)
    vip_name = _VIP_NAMES.get(vip_level, "None")
    title = doc.get("custom_title", "")
    partner = doc.get("partner_id", 0)
    games_won = doc.get("games_won", 0)
    games_lost = doc.get("games_lost", 0)
    total_games = games_won + games_lost
    win_rate = f"{(games_won/total_games)*100:.0f}%" if total_games > 0 else "N/A"
    inventory = doc.get("inventory", [])

    # Protection status
    protected = doc.get("protection_until", 0) > int(time.time())
    shield = "🛡️ Active" if protected else "❌ None"

    partner_text = f"`{partner}`" if partner else "💔 Single"

    text = (
        f"📋 **{name}'s Profile**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    if title:
        text += f"✨ *{title}*\n"
    text += (
        f"\n💰 **Economy**\n"
        f"  Wallet: **{wallet:,}** • Bank: **{bank:,}**\n"
        f"  Net Worth: **{net_worth:,}** coins\n"
        f"  Daily Streak: **{streak}** 🔥\n"
        f"\n⚔️ **Combat**\n"
        f"  K/D: **{kills}** / **{deaths}** (Ratio: {kd})\n"
        f"  Shield: {shield}\n"
        f"\n🎮 **Games**\n"
        f"  W/L: **{games_won}** / **{games_lost}** ({win_rate})\n"
        f"\n📊 **Stats**\n"
        f"  Level: **{level}** {xp_bar}\n"
        f"  VIP: {vip_name}\n"
        f"  Partner: {partner_text}\n"
        f"  Items: **{len(inventory)}**\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await message.reply_text(text, quote=True)


def _xp_progress_bar(xp: int, needed: int, length: int = 10) -> str:
    """Create a visual XP progress bar."""
    if needed <= 0:
        return "█" * length
    filled = int((xp / needed) * length)
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {xp}/{needed}"


@Client.on_message(filters.command("leaderboard"))
@error_handler
@rate_limit(5)
async def leaderboard_command(client: Client, message: Message):
    """Combined leaderboard — rich + kills in one view."""
    # Check cache
    cached = await get_cached("combined_lb")
    if cached:
        await message.reply_text(cached, quote=True)
        return

    top_rich = await get_top_users("wallet", limit=5)
    top_kills = await get_top_users("kills", limit=5)

    text = "🏆 **LEADERBOARD**\n━━━━━━━━━━━━━━━━━━\n\n"

    # Richest
    text += "💰 **Richest Players**\n"
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for i, doc in enumerate(top_rich):
        name = doc.get("name", "Unknown")[:15]
        text += f"  {medals[i]} `{name}` — **{doc.get('wallet', 0):,}**\n"
    if not top_rich:
        text += "  _No data yet_\n"

    text += "\n⚔️ **Top Killers**\n"
    for i, doc in enumerate(top_kills):
        name = doc.get("name", "Unknown")[:15]
        text += f"  {medals[i]} `{name}` — **{doc.get('kills', 0)}** kills\n"
    if not top_kills:
        text += "  _No data yet_\n"

    text += "\n━━━━━━━━━━━━━━━━━━"

    await set_cached("combined_lb", text)
    await message.reply_text(text, quote=True)

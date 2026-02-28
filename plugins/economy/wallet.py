"""
Auralyx Music — Economy: Wallet Commands
/daily, /bal, /give with atomic MongoDB operations.
Optimized for zero-lag text rendering.
"""

import logging
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from utils.cooldown import cooldown
from database.mongo import (
    ensure_user, get_user_economy, update_wallet, set_last_daily
)
from config import DAILY_AMOUNT
from utils.emojis import Emojis
from utils.reactions import send_reaction
from core.vip import identity

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("daily") & filters.group)
@error_handler
@rate_limit(3)
async def daily_command(client: Client, message: Message):
    """Claim daily coins with streak bonus."""
    user_id = message.from_user.id
    doc = await get_user_economy(user_id)

    last = doc.get("last_daily", 0)
    streak = doc.get("streak", 0)
    now = int(time.time())
    day_secs = 86400

    if now - last < day_secs:
        remaining = day_secs - (now - last)
        hours = remaining // 3600
        mins = (remainder := remaining % 3600) // 60
        await message.reply_text(
            f"📅 **DAILY CLAIM**\n"
            f"• Already claimed today.\n"
            f"• Come back in `{hours}h {mins}m`.",
            quote=True,
        )
        return

    # Streak logic
    if now - last < (day_secs * 2):
        new_streak = streak + 1
    else:
        new_streak = 1

    bonus = (new_streak - 1) * 250
    total_reward = DAILY_AMOUNT + bonus

    await update_wallet(user_id, total_reward)
    await set_last_daily(user_id, new_streak)
    
    streak_text = f"\n🔥 **Streak:** `{new_streak}` days (+{bonus:,} bonus)" if new_streak > 1 else ""

    await message.reply_text(
        f"✅ **DAILY CLAIMED!**\n"
        f"• Received: 💰 **{total_reward:,}** coins.{streak_text}",
        quote=True,
    )
    await send_reaction(client, message, "economy_daily")


@Client.on_message(filters.command("bal") & (filters.private | filters.group))
@error_handler
@rate_limit(3)
async def bal_command(client: Client, message: Message):
    """Check wallet and bank balance."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
    else:
        target = message.from_user

    doc = await get_user_economy(target.id)
    wallet = doc.get("wallet", 0)
    bank = doc.get("bank", 0)
    kills = doc.get("kills", 0)
    deaths = doc.get("deaths", 0)

    display_name = await identity.get_name(target.id, target.first_name)
    
    text = (
        f"💰 **COIN VAULT • 🏦**\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 {display_name}\n"
        f"━━━━━━━━━━━━━━\n"
        f"👛 **Wallet:** `{wallet:,}`\n"
        f"🏦 **Bank:** `{bank:,}`\n"
        f"⚔️ **Kills:** `{kills}` | 💀 **Deaths:** `{deaths}`\n"
        f"━━━━━━━━━━━━━━"
    )
    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("settitle") & filters.group)
@error_handler
@rate_limit(5)
async def set_title_command(client: Client, message: Message):
    """Set custom title."""
    if len(message.command) < 2:
        await message.reply_text(f"• Usage: `/settitle <text>`", quote=True)
        return

    title = " ".join(message.command[1:])
    if len(title) > 20:
        await message.reply_text(f"• Title too long! (Max 20 chars)", quote=True)
        return

    from database.mongo import set_custom_title
    await set_custom_title(message.from_user.id, title)
    
    await message.reply_text(f"✨ **Title Updated!**\n• New title: `{title}`", quote=True)


@Client.on_message(filters.command("give") & filters.group)
@error_handler
@rate_limit(5)
async def give_command(client: Client, message: Message):
    """Give coins to another user. Reply + amount OR /give <user> <amount>."""
    from utils.target import resolve_target

    sender_id = message.from_user.id

    # If replying, amount is the first arg
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
        if len(message.command) < 2:
            await message.reply_text("• Usage: reply + `/give <amount>`", quote=True)
            return
        try:
            amount = int(message.command[1])
        except ValueError:
            await message.reply_text("• Amount must be a number.", quote=True)
            return
    else:
        # /give <user> <amount>
        if len(message.command) < 3:
            await message.reply_text("• Usage: `/give <user_id|@user> <amount>` or reply + `/give <amount>`", quote=True)
            return
        target_id, target_name, extra = await resolve_target(client, message)
        if not target_id:
            await message.reply_text("• User not found.", quote=True)
            return
        try:
            amount = int(extra) if extra else int(message.command[2])
        except (ValueError, IndexError):
            await message.reply_text("• Amount must be a number.", quote=True)
            return

    if amount <= 0:
        await message.reply_text("• Amount must be positive.", quote=True)
        return

    if sender_id == target_id:
        return

    from database.mongo import atomic_update_wallet
    
    success = await atomic_update_wallet(sender_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Insufficient balance.", quote=True)
        return

    await update_wallet(target_id, amount)
    await message.reply_text(
        f"💸 **TRANSFER COMPLETE!**\n"
        f"• Sent: 💰 **{amount:,}** coins\n"
        f"• To: **{target_name}**",
        quote=True,
    )


@Client.on_message(filters.command("deposit") & filters.group)
@error_handler
@rate_limit(3)
async def deposit_command(client: Client, message: Message):
    """Deposit coins from wallet into bank."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/deposit <amount>` or `/deposit all`", quote=True)
        return

    user_id = message.from_user.id
    doc = await get_user_economy(user_id)
    wallet = doc.get("wallet", 0)

    if message.command[1].lower() == "all":
        amount = wallet
    else:
        try:
            amount = int(message.command[1])
        except ValueError:
            await message.reply_text("• Amount must be a number.", quote=True)
            return

    if amount <= 0:
        await message.reply_text("• Amount must be positive.", quote=True)
        return

    if amount > wallet:
        await message.reply_text("• Insufficient wallet balance.", quote=True)
        return

    from database.mongo import atomic_update_wallet, update_bank
    success = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Insufficient wallet balance.", quote=True)
        return

    await update_bank(user_id, amount)
    await message.reply_text(
        f"🏦 **DEPOSITED!**\n"
        f"• Moved 💰 **{amount:,}** to bank.",
        quote=True,
    )


@Client.on_message(filters.command("withdraw") & filters.group)
@error_handler
@rate_limit(3)
async def withdraw_command(client: Client, message: Message):
    """Withdraw coins from bank into wallet."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/withdraw <amount>` or `/withdraw all`", quote=True)
        return

    user_id = message.from_user.id
    doc = await get_user_economy(user_id)
    bank = doc.get("bank", 0)

    if message.command[1].lower() == "all":
        amount = bank
    else:
        try:
            amount = int(message.command[1])
        except ValueError:
            await message.reply_text("• Amount must be a number.", quote=True)
            return

    if amount <= 0:
        await message.reply_text("• Amount must be positive.", quote=True)
        return

    if amount > bank:
        await message.reply_text("• Insufficient bank balance.", quote=True)
        return

    from database.mongo import update_bank
    await update_bank(user_id, -amount)
    await update_wallet(user_id, amount)
    await message.reply_text(
        f"🏦 **WITHDRAWN!**\n"
        f"• Moved 💰 **{amount:,}** to wallet.",
        quote=True,
    )

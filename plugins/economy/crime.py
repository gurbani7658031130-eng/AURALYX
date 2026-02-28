"""
Auralyx Music — Economy: Crime Commands
/rob and /protect with cooldowns, success rate, and protection checks.
Optimized for zero-lag text rendering.
"""

import logging
import time
import random
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from utils.cooldown import cooldown
from database.mongo import (
    get_user_economy, update_wallet, is_protected, set_protection
)
from config import ROB_COOLDOWN, ROB_SUCCESS_RATE, ROB_MAX_STEAL, PROTECT_DURATION
from utils.emojis import Emojis
from utils.reactions import send_reaction

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("rob") & filters.group)
@error_handler
@rate_limit(5)
async def rob_command(client: Client, message: Message):
    """Rob another user. Reply or /rob <user_id|@username>."""
    from utils.target import resolve_target

    robber_id = message.from_user.id

    target_id, target_name, _ = await resolve_target(client, message)
    if not target_id:
        await message.reply_text(f"{Emojis.ERROR} Reply to a user or: `/rob <user_id|@user>`", quote=True)
        return

    if robber_id == target_id:
        await message.reply_text(f"{Emojis.ERROR} **You can't rob yourself.**", quote=True)
        return

    # Cooldown check
    allowed, remaining = cooldown.check(robber_id, "rob", ROB_COOLDOWN)
    if not allowed:
        await message.reply_text(f"{Emojis.TIME} **Cooldown!** Try again in `{remaining}s`.", quote=True)
        return

    # Protection check
    if await is_protected(target_id):
        await message.reply_text(f"{Emojis.PROTECT} **Target is protected!** Can't rob them.", quote=True)
        return

    target_doc = await get_user_economy(target_id)
    target_wallet = target_doc.get("wallet", 0)

    if target_wallet < 100:
        await message.reply_text(f"{Emojis.ERROR} **Target is too poor to rob.**", quote=True)
        return

    # Success chance
    if random.random() > ROB_SUCCESS_RATE:
        # Failed — robber loses some coins as penalty
        penalty = random.randint(50, 200)
        robber_doc = await get_user_economy(robber_id)
        actual_penalty = min(penalty, robber_doc.get("wallet", 0))
        if actual_penalty > 0:
            await update_wallet(robber_id, -actual_penalty)
        await message.reply_text(
            f"🚓 **ROB FAILED!**\n"
            f"• You got caught and lost 💰 **{actual_penalty:,}** coins.",
            quote=True,
        )
        await send_reaction(client, message, "economy_rob_fail")
        return

    # Success
    steal_amount = int(target_wallet * ROB_MAX_STEAL)
    steal_amount = max(steal_amount, 1)

    from database.mongo import atomic_update_wallet
    success = await atomic_update_wallet(target_id, -steal_amount, min_balance=0)
    if not success:
        await message.reply_text("• **Rob failed!** Target's wallet is too low.", quote=True)
        return

    await update_wallet(robber_id, steal_amount)

    await message.reply_text(
        f"🎭 **ROB SUCCESSFUL!**\n"
        f"• Stole 💰 **{steal_amount:,}** from **{target_name}**!",
        quote=True,
    )
    await send_reaction(client, message, "economy_rob_success")


@Client.on_message(filters.command("protect") & filters.group)
@error_handler
@rate_limit(5)
async def protect_command(client: Client, message: Message):
    """Activate a temporary protection shield."""
    user_id = message.from_user.id
    cost = 500

    if await is_protected(user_id):
        await message.reply_text(f"🛡️ **You're already protected!**", quote=True)
        return

    # Atomic check-and-deduct to prevent race conditions
    from database.mongo import atomic_update_wallet
    success = await atomic_update_wallet(user_id, -cost, min_balance=0)
    if not success:
        await message.reply_text(
            f"• **Insufficient funds.** Costs 💰 **{cost:,}**.",
            quote=True,
        )
        return

    until = int(time.time()) + PROTECT_DURATION
    await set_protection(user_id, until)

    minutes = PROTECT_DURATION // 60
    await message.reply_text(
        f"🛡️ **PROTECTION ACTIVATED!**\n"
        f"• Safe for **{minutes} minutes**.\n"
        f"• **Cost:** 💰 `{cost:,}`",
        quote=True,
    )

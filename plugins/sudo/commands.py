"""
Auralyx Music — Sudo Commands
Privileged economy management for SUDO_USERS only.
"""

import logging
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import sudo_only, error_handler
from database.mongo import (
    ensure_user, set_wallet, update_wallet, update_kills,
    reset_user_economy, wipe_all_economy, set_vip
)
from utils.emojis import Emojis

logger = logging.getLogger(__name__)

# Confirmation tracker for /wipeeconomy (Memory-bounded simple dict)
_wipe_pending: dict[int, float] = {} # user_id -> timestamp


def _get_target_id(message: Message) -> int | None:
    """Extract target user ID from reply or command arg."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if len(message.command) >= 2:
        try:
            return int(message.command[1])
        except ValueError:
            return None
    return None


@Client.on_message(filters.command("setcash"))
@error_handler
@sudo_only
async def setcash_command(client: Client, message: Message):
    """Set a user's wallet to an exact amount."""
    target_id = _get_target_id(message)
    if not target_id:
        await message.reply_text(f"{Emojis.ERROR} **Reply to a user or provide user ID.** `/setcash <id> <amount>`", quote=True)
        return

    # Amount is last arg
    try:
        amount = int(message.command[-1])
    except (ValueError, IndexError):
        await message.reply_text(f"{Emojis.ERROR} **Usage:** `/setcash <user_id> <amount>`", quote=True)
        return

    await ensure_user(target_id)
    await set_wallet(target_id, amount)
    await message.reply_text(f"{Emojis.SUCCESS} **Set wallet** for `{target_id}` to {Emojis.ECONOMY} **{amount:,}**.", quote=True)


@Client.on_message(filters.command("addcash"))
@error_handler
@sudo_only
async def addcash_command(client: Client, message: Message):
    """Add coins to a user's wallet."""
    target_id = _get_target_id(message)
    if not target_id:
        await message.reply_text("❌ **Reply to a user or provide user ID.**", quote=True)
        return

    try:
        amount = int(message.command[-1])
    except (ValueError, IndexError):
        await message.reply_text(f"{Emojis.ERROR} **Usage:** `/addcash <user_id> <amount>`", quote=True)
        return

    await update_wallet(target_id, amount)
    await message.reply_text(f"{Emojis.SUCCESS} **Added** {Emojis.ECONOMY} **{amount:,}** to user `{target_id}`.", quote=True)


@Client.on_message(filters.command("addkills"))
@error_handler
@sudo_only
async def addkills_command(client: Client, message: Message):
    """Add kills to a user."""
    target_id = _get_target_id(message)
    if not target_id:
        await message.reply_text("❌ **Reply to a user or provide user ID.**", quote=True)
        return

    try:
        amount = int(message.command[-1])
    except (ValueError, IndexError):
        await message.reply_text(f"{Emojis.ERROR} **Usage:** `/addkills <user_id> <amount>`", quote=True)
        return

    await update_kills(target_id, amount)
    await message.reply_text(f"{Emojis.SUCCESS} **Added** {Emojis.RPG} **{amount}** kills to user `{target_id}`.", quote=True)


@Client.on_message(filters.command("resetuser"))
@error_handler
@sudo_only
async def resetuser_command(client: Client, message: Message):
    """Reset a user's economy to defaults."""
    target_id = _get_target_id(message)
    if not target_id:
        await message.reply_text("❌ **Reply to a user or provide user ID.**", quote=True)
        return

    await reset_user_economy(target_id)
    await message.reply_text(f"{Emojis.SUCCESS} **Reset economy** for user `{target_id}`.", quote=True)


@Client.on_message(filters.command("wipeeconomy"))
@error_handler
@sudo_only
async def wipeeconomy_command(client: Client, message: Message):
    """Wipe ALL economy data. Requires double confirmation."""
    user_id = message.from_user.id
    now = time.time()

    last_time = _wipe_pending.get(user_id, 0)
    if now - last_time > 60: # TTL logic: 60 seconds
        _wipe_pending[user_id] = now
        await message.reply_text(
            f"{Emojis.WARNING} **DANGER: This will delete ALL economy data!**\n"
            "Send `/wipeeconomy` again within 60 seconds to confirm.",
            quote=True,
        )
        return

    # Second confirmation — execute
    _wipe_pending.pop(user_id, None)
    count = await wipe_all_economy()
    await message.reply_text(
        f"{Emojis.STOP} **Economy Wiped!**\n{Emojis.ARROW} Deleted **{count}** user records.",
        quote=True,
    )
    logger.warning("SUDO user %s wiped all economy data (%s records)", user_id, count)

@Client.on_message(filters.command("setvip"))
@error_handler
@sudo_only
async def setvip_command(client: Client, message: Message):
    """Set a user's VIP level. /setvip <id> <level> <days>"""
    target_id = _get_target_id(message)
    if not target_id:
        await message.reply_text(f"{Emojis.ERROR} **Reply to a user or provide user ID.**", quote=True)
        return

    # Usage: /setvip <id> <level> <days> 
    args = message.command[1:]
    if message.reply_to_message:
        # Args are [level, days]
        try:
            level = int(args[0])
            days = int(args[1]) if len(args) > 1 else 30
        except (ValueError, IndexError):
            await message.reply_text(f"{Emojis.ERROR} **Usage:** `/setvip <level> <days>` (replying)", quote=True)
            return
    else:
        # Args are [id, level, days]
        try:
            level = int(args[1])
            days = int(args[2]) if len(args) > 2 else 30
        except (ValueError, IndexError):
            await message.reply_text(f"{Emojis.ERROR} **Usage:** `/setvip <id> <level> <days>`", quote=True)
            return

    if level < 0 or level > 3:
        await message.reply_text(f"{Emojis.ERROR} **Level must be 0-3.** (0=None, 1=Silver, 2=Gold, 3=Platinum)", quote=True)
        return

    await set_vip(target_id, level, days)
    level_name = ["None", "Silver", "Gold", "Platinum"][level]
    await message.reply_text(
        f"{Emojis.SUCCESS} **VIP Set!**\n"
        f"{Emojis.ARROW} User: `{target_id}`\n"
        f"{Emojis.ARROW} Level: **{level_name}**\n"
        f"{Emojis.ARROW} Duration: **{days} days**",
        quote=True
    )
    logger.info("SUDO %s set VIP level %s for user %s", message.from_user.id, level, target_id)

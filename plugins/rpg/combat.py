"""
Auralyx Music — RPG: Combat
/kill and /revive with cooldowns, success chance, and protection.
All commands support: reply, user ID, or @username.
"""

import logging
import random
import time
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from utils.cooldown import cooldown
from utils.target import resolve_target
from database.mongo import (
    get_user_economy, update_kills, update_deaths, is_protected, ensure_user
)
from config import KILL_COOLDOWN, KILL_SUCCESS_RATE
from utils.emojis import Emojis
from utils.reactions import send_reaction
from core.vip import identity

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("kill") & filters.group)
@error_handler
@rate_limit(5)
async def kill_command(client: Client, message: Message):
    """Attempt to kill another user. Reply or /kill <user_id|@username>."""
    attacker_id = message.from_user.id

    target_id, target_name, _ = await resolve_target(client, message)
    if not target_id:
        await message.reply_text(f"{Emojis.ERROR} Reply to a user or: `/kill <user_id|@user>`", quote=True)
        return

    if attacker_id == target_id:
        await message.reply_text(f"{Emojis.ERROR} **You can't kill yourself.**", quote=True)
        return

    # Cooldown
    allowed, remaining = cooldown.check(attacker_id, "kill", KILL_COOLDOWN)
    if not allowed:
        await message.reply_text(f"{Emojis.TIME} **Cooldown!** Try again in `{remaining}s`.", quote=True)
        return

    # Protection check
    if await is_protected(target_id):
        await message.reply_text(f"{Emojis.PROTECT} **Target is protected!** Can't attack them.", quote=True)
        return

    # Ensure both users exist
    await ensure_user(attacker_id, message.from_user.first_name)
    await ensure_user(target_id, target_name)

    # Success chance
    if random.random() > KILL_SUCCESS_RATE:
        # Failed — attacker dies instead
        await update_deaths(attacker_id)
        
        attacker_display = await identity.get_name(attacker_id, message.from_user.first_name)
        text = (
            f"⚔️ **ATTACK FAILED!**\n"
            f"• {attacker_display} tripped and died instead.\n"
            f"• **Stats:** +1 Death."
        )
        await message.reply_text(text, quote=True)
        await send_reaction(client, message, "rpg_death")
        return

    # Success
    await update_kills(attacker_id)
    await update_deaths(target_id)

    attacker_display = await identity.get_name(attacker_id, message.from_user.first_name)
    target_display = await identity.get_name(target_id, target_name)
    
    text = (
        f"⚔️ **KILL SUCCESSFUL!**\n"
        f"• {attacker_display} killed {target_display}!\n"
        f"• **Stats:** +1 Kill for attacker, +1 Death for target."
    )
    await message.reply_text(text, quote=True)
    await send_reaction(client, message, "rpg_kill")


@Client.on_message(filters.command("revive") & filters.group)
@error_handler
@rate_limit(5)
async def revive_command(client: Client, message: Message):
    """Revive a user (removes 1 death). Reply, user ID, or self."""
    target_id, target_name, _ = await resolve_target(client, message)

    # Fallback to self if no target provided
    if not target_id:
        target_id = message.from_user.id
        target_name = message.from_user.first_name

    doc = await get_user_economy(target_id)
    deaths = doc.get("deaths", 0)

    if deaths <= 0:
        await message.reply_text(f"{Emojis.SUCCESS} **{target_name}** has no deaths to revive from.", quote=True)
        return

    await update_deaths(target_id, -1)

    target_display = await identity.get_name(target_id, target_name)
    text = (
        f"✨ **REVIVED!**\n"
        f"• {target_display} lost 1 death.\n"
        f"• **Current Deaths:** `{max(0, deaths - 1)}`"
    )
    await message.reply_text(text, quote=True)
    await send_reaction(client, message, "music_start")

"""
Auralyx Music — Owner: Economy Overrides
/o_give, /o_reset
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import owner_only, error_handler, owner_rate_limit
from database.mongo import update_wallet, reset_user_economy, ensure_user
from utils.emojis import Emojis
from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("o_give") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(2)
@error_handler
async def owner_give(client: Client, message: Message):
    """Give unlimited coins to a user."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"💎 **OWNER LOG**: `/o_give` by `{message.from_user.id}`")
        except: pass
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ **Usage:** `/o_give <user_id> <amount>`")
        return
        
    try:
        target_id = int(args[1])
        amount = int(args[2])
    except ValueError:
        await message.reply_text("❌ **Invalid user_id or amount.**")
        return
        
    await update_wallet(target_id, amount)
    await message.reply_text(f"💎 **Transaction Complete.**\nAdded `{amount:,}` coins to `{target_id}`.")


@Client.on_message(filters.command("o_reset") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_reset(client: Client, message: Message):
    """Reset a user's economy profile."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"🧹 **OWNER LOG**: `/o_reset` by `{message.from_user.id}`")
        except: pass
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ **Usage:** `/o_reset <user_id>`")
        return
        
    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ **Invalid user_id.**")
        return
        
    await reset_user_economy(target_id)
    await message.reply_text(f"🧹 **Profile Reset.**\nUser `{target_id}` has been wiped to defaults.")

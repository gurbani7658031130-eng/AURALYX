"""
Auralyx Music — Owner: Shadowban Controls
/o_shadowban, /o_unshadow
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import owner_only, error_handler, owner_rate_limit
from core.shadowban import shadow_ban, shadow_unban
from utils.emojis import Emojis
from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("o_shadowban") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_shadowban(client: Client, message: Message):
    """Silently block a user from using the bot."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"👤 **OWNER LOG**: `/o_shadowban` by `{message.from_user.id}`")
        except: pass
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ **Usage:** `/o_shadowban <user_id>`")
        return
        
    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ **Invalid user_id.**")
        return
        
    await shadow_ban(target_id)
    await message.reply_text(f"👤 **Shadowban Applied.**\nUser `{target_id}` is now silently blocked.")


@Client.on_message(filters.command("o_unshadow") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_unshadow(client: Client, message: Message):
    """Unblock a shadowbanned user."""
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(LOG_CHANNEL_ID, f"✅ **OWNER LOG**: `/o_unshadow` by `{message.from_user.id}`")
        except: pass
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ **Usage:** `/o_unshadow <user_id>`")
        return
        
    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ **Invalid user_id.**")
        return
        
    await shadow_unban(target_id)
    await message.reply_text(f"✅ **Shadowban Lifted.**\nUser `{target_id}` can now interact again.")

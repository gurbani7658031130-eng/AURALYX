"""
Auralyx Music — Sudo: Maintenance
Toggles maintenance mode across the bot.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import sudo_only, error_handler
from core.maintenance import set_maintenance, is_maintenance
from utils.emojis import Emojis

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("maintenance") & (filters.private | filters.group))
@sudo_only
@error_handler
async def maintenance_command(client: Client, message: Message):
    """Toggle maintenance mode on/off."""
    args = message.text.split()
    if len(args) < 2:
        status = "ON" if is_maintenance() else "OFF"
        await message.reply_text(f"🚧 **Maintenance is currently**: `{status}`\nUse `/maintenance on` or `/maintenance off`.")
        return

    cmd = args[1].lower()
    if cmd == "on":
        await set_maintenance(True)
        await message.reply_text("🚧 **Maintenance Mode ENABLED.**\nNon-sudo commands are now blocked.")
    elif cmd == "off":
        await set_maintenance(False)
        await message.reply_text("✅ **Maintenance Mode DISABLED.**\nAll commands are available.")
    else:
        await message.reply_text("❌ **Invalid usage.** Use `/maintenance on` or `off`.")

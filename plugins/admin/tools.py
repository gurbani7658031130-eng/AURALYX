"""
Auralyx Music — Utility Tools
Command: /getid
Helps users find Custom Emoji IDs by replying to an emoji.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from config import SUDO_USERS

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("getid"))
async def get_emoji_id(client: Client, message: Message):
    """Get the Custom Emoji ID from a replied message or a message containing emojis."""
    
    target = message.reply_to_message or message
    
    if not target.entities:
        await message.reply_text(
            "❌ **No entities found.**\n"
            "Reply to a message containing a **Custom Emoji** or send one with the command.",
            quote=True
        )
        return

    found = []
    seen = set()
    for entity in target.entities:
        if entity.type.name == "CUSTOM_EMOJI" or entity.type == "custom_emoji":
            emoji_id = str(entity.custom_emoji_id)
            if emoji_id not in seen:
                found.append(f"• `{emoji_id}`")
                seen.add(emoji_id)

    if not found:
        await message.reply_text("❌ **No Custom Emojis detected in that message.**", quote=True)
    else:
        # Save to file
        try:
            with open("extracted_emojis.txt", "a", encoding="utf-8") as f:
                f.write(f"\n# Extracted from message: {target.id}\n")
                for eid in seen:
                    f.write(f"{eid}\n")
        except Exception as e:
            logger.error("Failed to save emoji IDs: %s", e)

        text = f"**💎 Found {len(found)} Unique Custom Emoji IDs:**\n\n" + "\n".join(found)
        text += "\n\n✅ Saved to `extracted_emojis.txt`!"
        await message.reply_text(text, quote=True)

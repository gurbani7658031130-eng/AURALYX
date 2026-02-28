"""
Auralyx Music — Reaction System
Handles contextual message reactions for various bot actions.
"""

import random
import logging
from typing import List, Union, Optional
from pyrogram import Client
from pyrogram.types import Message
from config import ENABLE_PREMIUM_EFFECTS

logger = logging.getLogger(__name__)

# Reaction Mappings
REACTIONS = {
    "music_start": ["🎵", "🔥", "🎧"],
    "music_skip": ["⏭", "👍", "👌"],
    "music_queue": ["📋", "➕"],
    "economy_daily": ["💰", "🎰", "✨"],
    "economy_rob_success": ["🗡", "🎭", "🏃"],
    "economy_rob_fail": ["🤡", "🚓", "❌"],
    "rpg_kill": ["💀", "⚔️", "💥"],
    "rpg_death": ["👼", "🥀", "⚰️"],
    "admin_promote": ["👑", "✅"],
    "admin_demote": ["🔽", "🚫"],
}

async def send_reaction(client: Client, message: Message, reaction_key: str):
    """
    Send a random reaction to a message based on a key.
    
    Args:
        client: Pyrogram Client.
        message: The message to react to.
        reaction_key: Key from the REACTIONS mapping.
    """
    if not ENABLE_PREMIUM_EFFECTS:
        return

    choices = REACTIONS.get(reaction_key, ["👍"])
    emoji = random.choice(choices)

    try:
        # custom_emoji_id can be passed if we had premium IDs for reactions.
        # For now, we use standard Unicode or placeholders if platform supports.
        await message.react(emoji)
    except Exception as e:
        logger.debug("Failed to send reaction to message %s: %s", message.id, e)

# Helper for direct custom emoji reaction if ID is known
async def send_premium_reaction(client: Client, message: Message, emoji_id: Union[int, str]):
    """Send a custom emoji reaction."""
    if not ENABLE_PREMIUM_EFFECTS:
        return
        
    try:
        await message.react(int(emoji_id))
    except Exception as e:
        logger.debug("Failed to send premium reaction %s: %s", emoji_id, e)

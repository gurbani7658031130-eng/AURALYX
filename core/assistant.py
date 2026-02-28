"""
Auralyx Music — Assistant / Userbot Client
Secondary Pyrogram client used as the PyTgCalls bridge for voice chats.
"""

import logging
from pyrogram import Client
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)


class AuralyxAssistant(Client):
    """
    Userbot client that joins voice chats on behalf of the bot.

    NOTE: This client requires a SESSION_STRING for production use.
    For now it is scaffolded — provide SESSION_STRING via env when ready.
    """

    def __init__(self):
        import os
        import sys

        session_string = os.getenv("SESSION_STRING", "")
        if not session_string:
            logger.critical("SESSION_STRING is missing in .env! The Assistant cannot start without it.")
            logger.critical("Run 'python gen_session.py' to get one and add it to .env.")
            sys.exit(1)

        super().__init__(
            name="AuralyxAssistant",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True,
        )
        logger.info("AuralyxAssistant client initialized.")

    async def start(self):
        await super().start()
        me = await self.get_me()
        logger.info(
            "Assistant started as %s (ID: %s)",
            me.first_name,
            me.id,
        )

    async def stop(self):
        await super().stop()
        logger.info("Assistant stopped.")


# Export a single instance
assistant = AuralyxAssistant()

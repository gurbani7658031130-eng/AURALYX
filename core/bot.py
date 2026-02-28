"""
Auralyx Music - Bot Client
Pyrogram bot client with global middleware.
"""

import logging
import time
from pyrogram import Client

from config import API_HASH, API_ID, BOT_TOKEN, OWNER_ID
from core.pmpermit import is_pm_permitted
from core.sudo_acl import is_approved_user, is_sudo

logger = logging.getLogger(__name__)
_seen_updates: dict[tuple[int, int], float] = {}
_seen_callbacks: dict[str, float] = {}


class AuralyxBot(Client):
    """Main Telegram bot client powered by Pyrogram."""

    def __init__(self):
        super().__init__(
            name="AuralyxBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=True,
            plugins=dict(root="plugins"),
            workers=20,
        )
        logger.info("AuralyxBot client initialized.")

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.me = me
        logger.info("Bot started as @%s (ID: %s)", me.username, me.id)

    async def stop(self):
        await super().stop()
        logger.info("Bot stopped.")

    async def _check_access(self, update):
        """Global access control for all message/callback updates."""
        from core.maintenance import is_maintenance
        from core.shadowban import is_shadowbanned

        user = update.from_user
        if not user:
            return True

        user_id = user.id
        if user_id == OWNER_ID:
            return True

        # Private message control.
        if getattr(update, "chat", None) and getattr(update.chat, "type", None) == "private":
            if not await is_pm_permitted() and not await is_approved_user(user_id):
                from pyrogram.types import Message

                if isinstance(update, Message):
                    try:
                        await update.reply_text("Private messages are disabled by owner.", quote=True)
                    except Exception:
                        pass
                elif hasattr(update, "answer"):
                    try:
                        await update.answer("PM disabled by owner.", show_alert=True)
                    except Exception:
                        pass
                return False

        if is_shadowbanned(user_id):
            return False

        if is_maintenance() and not await is_approved_user(user_id):
            from pyrogram.types import Message

            if isinstance(update, Message):
                try:
                    await update.reply_text(
                        "Bot is under maintenance. Please try again later.",
                        quote=True,
                    )
                except Exception:
                    pass
            elif hasattr(update, "answer"):
                try:
                    await update.answer("Maintenance Mode", show_alert=True)
                except Exception:
                    pass
            return False

        return True

    async def on_message(self, message):
        # Guard against duplicate update delivery.
        key = (message.chat.id if message.chat else 0, message.id or 0)
        now = time.monotonic()
        for k, ts in list(_seen_updates.items()):
            if now - ts > 20:
                _seen_updates.pop(k, None)
        if key in _seen_updates:
            return
        _seen_updates[key] = now

        if not await self._check_access(message):
            return
        await super().on_message(message)

    async def on_callback_query(self, callback_query):
        cb_id = getattr(callback_query, "id", "")
        if cb_id:
            now = time.monotonic()
            for k, ts in list(_seen_callbacks.items()):
                if now - ts > 20:
                    _seen_callbacks.pop(k, None)
            if cb_id in _seen_callbacks:
                return
            _seen_callbacks[cb_id] = now

        if not await self._check_access(callback_query):
            return
        await super().on_callback_query(callback_query)

    async def on_edited_message(self, message):
        if not await self._check_access(message):
            return
        await super().on_edited_message(message)

    async def on_inline_query(self, inline_query):
        if not await self._check_access(inline_query):
            return
        await super().on_inline_query(inline_query)

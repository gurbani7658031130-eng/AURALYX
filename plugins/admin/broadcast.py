"""
Auralyx Music - Admin: Broadcast
/broadcast command for sending text or copied messages to all registered groups.
"""

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from config import OWNER_ID
from database.mongo import get_all_groups
from utils.decorators import error_handler

logger = logging.getLogger(__name__)


async def _send_broadcast_to_chat(
    client: Client,
    chat_id: int,
    copy_mode: bool,
    reply_msg: Message | None,
    text: str,
) -> Message:
    """Send one broadcast item and return the destination message."""
    if copy_mode and reply_msg:
        return await client.copy_message(
            chat_id=chat_id,
            from_chat_id=reply_msg.chat.id,
            message_id=reply_msg.id,
        )
    return await client.send_message(chat_id, text)


@Client.on_message(filters.command("broadcast") & filters.private)
@error_handler
async def broadcast_command(client: Client, message: Message):
    """
    Broadcast to all registered groups. Owner only.

    Modes:
    - Text mode: /broadcast <message>
    - Copy mode: reply to any message (text/photo/video/voice/sticker/etc) with /broadcast
    """
    if not message.from_user or message.from_user.id != OWNER_ID:
        await message.reply_text("Owner only.", quote=True)
        return

    reply_msg = message.reply_to_message
    broadcast_text = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""

    if not reply_msg and not broadcast_text:
        await message.reply_text(
            "Usage: `/broadcast <message>`\n"
            "Or reply to any message with `/broadcast`.",
            quote=True,
        )
        return

    groups = await get_all_groups()
    if not groups:
        await message.reply_text("No groups registered.", quote=True)
        return

    status_msg = await message.reply_text(f"Broadcasting to {len(groups)} groups...", quote=True)

    sent = 0
    failed = 0
    copy_mode = reply_msg is not None

    for chat_id in groups:
        try:
            await _send_broadcast_to_chat(client, chat_id, copy_mode, reply_msg, broadcast_text)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await _send_broadcast_to_chat(client, chat_id, copy_mode, reply_msg, broadcast_text)
                sent += 1
            except Exception as retry_err:
                logger.warning("Broadcast retry failed for %s: %s", chat_id, retry_err)
                failed += 1
        except Exception as e:
            logger.warning("Broadcast failed for %s: %s", chat_id, e)
            failed += 1

        await asyncio.sleep(0.3)

    await status_msg.edit_text(
        "Broadcast complete.\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}"
    )


@Client.on_message(filters.command(["broadcastpin", "bpin"]) & filters.private)
@error_handler
async def broadcast_pin_command(client: Client, message: Message):
    """
    Broadcast and pin in all registered groups. Owner only.

    Modes:
    - Text mode: /broadcastpin <message>
    - Copy mode: reply to any message and send /broadcastpin
    """
    if not message.from_user or message.from_user.id != OWNER_ID:
        await message.reply_text("Owner only.", quote=True)
        return

    reply_msg = message.reply_to_message
    broadcast_text = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""

    if not reply_msg and not broadcast_text:
        await message.reply_text(
            "Usage: `/broadcastpin <message>`\n"
            "Or reply to any message with `/broadcastpin`.",
            quote=True,
        )
        return

    groups = await get_all_groups()
    if not groups:
        await message.reply_text("No groups registered.", quote=True)
        return

    status_msg = await message.reply_text(f"Broadcast+pin to {len(groups)} groups...", quote=True)

    sent = 0
    failed = 0
    pinned = 0
    pin_failed = 0
    copy_mode = reply_msg is not None

    for chat_id in groups:
        try:
            out = await _send_broadcast_to_chat(client, chat_id, copy_mode, reply_msg, broadcast_text)
            sent += 1
            try:
                await client.pin_chat_message(
                    chat_id=chat_id,
                    message_id=out.id,
                    disable_notification=True,
                )
                pinned += 1
            except Exception as pin_err:
                logger.warning("Pin failed for %s: %s", chat_id, pin_err)
                pin_failed += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                out = await _send_broadcast_to_chat(client, chat_id, copy_mode, reply_msg, broadcast_text)
                sent += 1
                try:
                    await client.pin_chat_message(
                        chat_id=chat_id,
                        message_id=out.id,
                        disable_notification=True,
                    )
                    pinned += 1
                except Exception as pin_err:
                    logger.warning("Pin failed after retry for %s: %s", chat_id, pin_err)
                    pin_failed += 1
            except Exception as retry_err:
                logger.warning("Broadcastpin retry failed for %s: %s", chat_id, retry_err)
                failed += 1
        except Exception as e:
            logger.warning("Broadcastpin failed for %s: %s", chat_id, e)
            failed += 1

        await asyncio.sleep(0.3)

    await status_msg.edit_text(
        "Broadcast+pin complete.\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}\n"
        f"Pinned: {pinned}\n"
        f"Pin Failed: {pin_failed}"
    )

"""
Auralyx Music — Admin: Group Management
/promote and /demote with permission checks.
Updated to pure text for zero processing lag.
"""

import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, ChatPrivileges
from core.permissions import admin_only
from utils.decorators import error_handler
from utils.reactions import send_reaction

logger = logging.getLogger(__name__)


async def can_bot_promote(client: Client, chat_id: int) -> bool:
    """Check if the bot has can_promote_members permission."""
    try:
        bot_member = await client.get_chat_member(chat_id, client.me.id)
        if bot_member.privileges and bot_member.privileges.can_promote_members:
            return True
        return False
    except Exception as e:
        logger.warning("Bot permission check failed in %s: %s", chat_id, e)
        return False


@Client.on_message(filters.command("promote") & filters.group)
@error_handler
async def promote_command(client: Client, message: Message):
    """Promote a user with limited admin rights."""
    if not await admin_only(client, message):
        return

    if not message.reply_to_message:
        await message.reply_text("• Reply to a user to promote.", quote=True)
        return

    chat_id = message.chat.id
    target = message.reply_to_message.from_user

    if not target:
        return

    if not await can_bot_promote(client, chat_id):
        await message.reply_text("• I need 'Add Admins' permission.", quote=True)
        return

    try:
        await client.promote_chat_member(
            chat_id,
            target.id,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_restrict_members=True,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=True,
                is_anonymous=False,
            )
        )
        await message.reply_text(f"✅ **Promoted** {target.mention}.", quote=True)
        await send_reaction(client, message, "admin_promote")
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("demote") & filters.group)
@error_handler
async def demote_command(client: Client, message: Message):
    """Demote a user removing admin rights."""
    if not await admin_only(client, message):
        return

    if not message.reply_to_message:
        await message.reply_text("• Reply to a user to demote.", quote=True)
        return

    chat_id = message.chat.id
    target = message.reply_to_message.from_user

    if not target:
        return

    if not await can_bot_promote(client, chat_id):
        await message.reply_text("• I need 'Add Admins' permission.", quote=True)
        return

    try:
        await client.promote_chat_member(
            chat_id,
            target.id,
            privileges=ChatPrivileges(
                can_manage_chat=False,
                can_delete_messages=False,
                can_manage_video_chats=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
                is_anonymous=False,
            )
        )
        await message.reply_text(f"✅ **Demoted** {target.mention}.", quote=True)
        await send_reaction(client, message, "admin_demote")
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)

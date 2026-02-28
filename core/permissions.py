"""
Auralyx Music — Permission Helpers
Owner and admin checks used across the bot.

Security model:
  - OWNER_ID has autonomous privilege (bypasses everything)
  - SUDO_USERS can use admin commands via the bot
  - Group admins can ONLY use admin commands if they are also owner/sudo
    This prevents random group admins from abusing bot admin powers.
"""

import logging
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
from config import OWNER_ID
from core.sudo_acl import is_sudo

logger = logging.getLogger(__name__)


def is_owner(user_id: int) -> bool:
    """Check if the given user_id matches the bot owner."""
    return user_id == OWNER_ID


def is_approved(user_id: int) -> bool:
    """Check if user is owner or an approved (sudo) user."""
    return user_id == OWNER_ID


async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """
    Check if a user is an admin (or owner) in a group chat.
    Returns True for OWNER_ID regardless of group membership.
    """
    if is_owner(user_id):
        return True

    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception as e:
        logger.warning("Admin check failed for user %s in chat %s: %s", user_id, chat_id, e)
        return False


async def owner_only(message: Message) -> bool:
    """
    Returns True if the sender is the owner.
    Otherwise replies with an access-denied message.
    """
    if is_owner(message.from_user.id):
        return True
    await message.reply_text("⛔ **Access Denied** — Owner only.", quote=True)
    return False


async def admin_only(client: Client, message: Message) -> bool:
    """
    Restricted admin check:
    - Owner always passes
    - Sudo users always pass
    - Group admins ONLY pass if they are also owner/sudo
    
    This prevents random group admins from using the bot's admin
    powers (ban, mute, kick, etc.) unless they are approved.
    """
    user_id = message.from_user.id

    # Owner has autonomous privilege
    if is_owner(user_id):
        return True

    # Sudo users are approved operators
    if await is_sudo(user_id):
        return True

    # Regular group admins are NOT allowed to use bot admin commands
    # They must be added to SUDO_USERS to be approved
    await message.reply_text(
        "⛔ **Access Denied** — Only approved operators can use admin commands.\n"
        "Contact the bot owner to get approved.",
        quote=True,
    )
    return False

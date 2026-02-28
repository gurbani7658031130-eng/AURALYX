"""
Auralyx Music — Admin: Warning System
/warn, /unwarn, /warnings — 3 warns = auto-mute

All commands support: reply to user OR /warn <user_id|@username> [reason]
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from core.permissions import admin_only
from utils.decorators import error_handler
from database.mongo import add_warning, remove_warning, get_warnings, clear_warnings

logger = logging.getLogger(__name__)

MAX_WARNINGS = 3  # Auto-mute after this many


async def _resolve_target(client: Client, message: Message):
    """Resolve target from reply or argument."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        reason = " ".join(message.command[1:]) or "No reason"
        return target.id, target.mention, reason

    if len(message.command) >= 2:
        identifier = message.command[1]
        reason = " ".join(message.command[2:]) or "No reason"
        try:
            user_id = int(identifier)
            try:
                user = await client.get_users(user_id)
                return user_id, user.mention, reason
            except Exception:
                return user_id, f"`{user_id}`", reason
        except ValueError:
            pass
        if identifier.startswith("@"):
            try:
                user = await client.get_users(identifier)
                return user.id, user.mention, reason
            except Exception:
                pass

    return None, None, None


@Client.on_message(filters.command("warn") & filters.group)
@error_handler
async def warn_command(client: Client, message: Message):
    """Warn a user. 3 warns = auto-mute. Usage: reply or /warn <id> [reason]"""
    if not await admin_only(client, message):
        return

    user_id, name, reason = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/warn <user_id> [reason]`", quote=True)
        return

    chat_id = message.chat.id
    count = await add_warning(chat_id, user_id, reason)

    if count >= MAX_WARNINGS:
        try:
            await client.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions()
            )
            await clear_warnings(chat_id, user_id)
            await message.reply_text(
                f"⚠️ {name} reached **{MAX_WARNINGS}** warnings!\n"
                f"🔇 **Auto-muted.** Warnings cleared.",
                quote=True,
            )
        except Exception as e:
            await message.reply_text(
                f"⚠️ Warning {count}/{MAX_WARNINGS} for {name}\n"
                f"• Auto-mute failed: `{e}`",
                quote=True,
            )
    else:
        await message.reply_text(
            f"⚠️ **Warning {count}/{MAX_WARNINGS}** for {name}\n"
            f"• Reason: _{reason}_",
            quote=True,
        )


@Client.on_message(filters.command("unwarn") & filters.group)
@error_handler
async def unwarn_command(client: Client, message: Message):
    """Remove one warning. Usage: reply or /unwarn <user_id>"""
    if not await admin_only(client, message):
        return

    user_id, name, _ = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/unwarn <user_id>`", quote=True)
        return

    removed = await remove_warning(message.chat.id, user_id)
    if removed:
        warns = await get_warnings(message.chat.id, user_id)
        await message.reply_text(
            f"✅ Removed 1 warning from {name}\n"
            f"• Remaining: **{len(warns)}/{MAX_WARNINGS}**",
            quote=True,
        )
    else:
        await message.reply_text(f"• {name} has no warnings.", quote=True)


@Client.on_message(filters.command("warnings") & filters.group)
@error_handler
async def warnings_command(client: Client, message: Message):
    """View warnings. Usage: reply or /warnings <user_id>"""
    user_id, name, _ = await _resolve_target(client, message)
    if not user_id:
        await message.reply_text("• Reply to a user or: `/warnings <user_id>`", quote=True)
        return

    warns = await get_warnings(message.chat.id, user_id)
    if not warns:
        await message.reply_text(f"✅ {name} has **no warnings**.", quote=True)
        return

    text = f"⚠️ **Warnings for {name}** ({len(warns)}/{MAX_WARNINGS})\n━━━━━━━━━━━━━━\n"
    for i, w in enumerate(warns[:10], 1):
        reason = w.get("reason", "No reason")
        text += f"  {i}. _{reason}_\n"

    await message.reply_text(text, quote=True)

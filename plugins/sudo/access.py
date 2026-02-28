"""Approval panel + selected sudo/global commands."""

import asyncio
import logging
import os
import sys
import time

from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait
from pyrogram.types import (
    CallbackQuery,
    ChatPermissions,
    ChatPrivileges,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import OWNER_ID
from core.pmpermit import is_pm_permitted, set_pm_permit
from core.sudo_acl import (
    AVAILABLE_PERMISSIONS,
    approve_user,
    disapprove_user,
    get_permissions,
    has_permission,
    is_approved_user,
    is_sudo,
    list_approved_users,
    set_permissions,
)
from database.approval_sqlite import is_user_approved
from database.mongo import get_all_groups
from utils.decorators import error_handler, permission_required, sudo_only

logger = logging.getLogger(__name__)

_PANEL_PERMISSIONS = ["ban", "mute", "broadcast", "stats", "restart", "logs"]
_SESSION_TTL = 600

# owner_id -> session
approval_sessions: dict[int, dict] = {}
warroom_sessions: dict[int, dict] = {}  # message_id -> {"owner_id": int, "expires_at": float}


def _perm_enabled(session: dict, key: str) -> bool:
    return key in session.get("selected_permissions", set())


def _panel_text(session: dict) -> str:
    target_label = session.get("target_label", "Unknown")
    target_id = session.get("target_user_id", 0)
    return (
        "Permission Setup\n\n"
        f"User: {target_label}\n"
        f"ID: {target_id}"
    )


def _panel_markup(session: dict) -> InlineKeyboardMarkup:
    def btn(key: str, label: str) -> InlineKeyboardButton:
        icon = "ON" if _perm_enabled(session, key) else "OFF"
        return InlineKeyboardButton(f"{label} [{icon}]", callback_data=f"ap:t:{key}")

    rows = [
        [btn("ban", "Ban"), btn("mute", "Mute")],
        [btn("broadcast", "Broadcast"), btn("stats", "Stats")],
        [btn("restart", "Restart"), btn("logs", "Logs")],
        [InlineKeyboardButton("Confirm", callback_data="ap:c"), InlineKeyboardButton("Cancel", callback_data="ap:x")],
    ]
    return InlineKeyboardMarkup(rows)


def _get_session(owner_id: int) -> dict | None:
    session = approval_sessions.get(owner_id)
    if not session:
        return None
    if time.time() > session.get("expires_at", 0):
        approval_sessions.pop(owner_id, None)
        return None
    return session


def _get_warroom(message_id: int) -> dict | None:
    session = warroom_sessions.get(message_id)
    if not session:
        return None
    if time.time() > session.get("expires_at", 0):
        warroom_sessions.pop(message_id, None)
        return None
    return session


def _parse_permission_args(raw: str) -> list[str]:
    """
    Parse comma/space separated permissions and keep only known keys.
    Example: "ban, mute stats" -> ["ban", "mute", "stats"]
    """
    parts = [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]
    out = []
    for p in parts:
        if p in AVAILABLE_PERMISSIONS and p not in out:
            out.append(p)
    return out


async def _resolve_target_user(client: Client, message: Message) -> tuple[int | None, str]:
    """Resolve target from reply, user_id, or @username."""
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        label = f"@{u.username}" if u.username else f"{u.first_name or 'Unknown'}"
        return int(u.id), label

    if len(message.command) < 2:
        return None, ""

    raw = message.command[1].strip()
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        uid = int(raw)
        try:
            user = await client.get_users(uid)
            label = f"@{user.username}" if user.username else f"{user.first_name or uid}"
            return uid, label
        except Exception:
            return uid, str(uid)

    username = raw[1:] if raw.startswith("@") else raw
    try:
        user = await client.get_users(username)
        label = f"@{user.username}" if user.username else f"{user.first_name or username}"
        return int(user.id), label
    except Exception:
        return None, ""


@Client.on_message(filters.command("approve") & (filters.private | filters.group | filters.channel))
@error_handler
async def approve_command(client: Client, message: Message):
    """Owner-only permission panel for global approvals."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/approve <user_id|@username>` or reply to user.", quote=True)

    if target_id == OWNER_ID:
        return await message.reply_text("Owner cannot approve themselves.", quote=True)

    if await is_user_approved(target_id):
        return await message.reply_text("User is already approved.", quote=True)

    approval_sessions[message.from_user.id] = {
        "target_user_id": int(target_id),
        "target_label": target_label or str(target_id),
        "selected_permissions": set(),
        "created_at": time.time(),
        "expires_at": time.time() + _SESSION_TTL,
    }

    await message.reply_text(
        _panel_text(approval_sessions[message.from_user.id]),
        quote=True,
        reply_markup=_panel_markup(approval_sessions[message.from_user.id]),
    )


@Client.on_callback_query(filters.regex(r"^ap:(t:[a-z_]+|c|x)$"))
async def approve_panel_callback(client: Client, callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != OWNER_ID:
        return await callback.answer("Owner only.", show_alert=True)

    session = _get_session(callback.from_user.id)
    if not session:
        return await callback.answer("Approval session expired. Run /approve again.", show_alert=True)

    data = callback.data
    if data.startswith("ap:t:"):
        key = data.split(":", 2)[2]
        if key not in _PANEL_PERMISSIONS:
            return await callback.answer("Invalid permission key.", show_alert=True)

        perms: set[str] = session["selected_permissions"]
        if key in perms:
            perms.remove(key)
        else:
            perms.add(key)

        session["expires_at"] = time.time() + _SESSION_TTL
        await callback.message.edit_text(_panel_text(session), reply_markup=_panel_markup(session))
        return await callback.answer("Updated")

    if data == "ap:x":
        approval_sessions.pop(callback.from_user.id, None)
        await callback.message.edit_text("Approval cancelled.")
        return await callback.answer("Cancelled")

    if data == "ap:c":
        perms = sorted(p for p in session.get("selected_permissions", set()) if p in AVAILABLE_PERMISSIONS)
        if not perms:
            return await callback.answer("Select at least one permission before confirm.", show_alert=True)

        target_id = int(session["target_user_id"])
        ok = await approve_user(
            user_id=target_id,
            approved_by=callback.from_user.id,
            permissions=perms,
        )

        approval_sessions.pop(callback.from_user.id, None)

        if not ok:
            await callback.message.edit_text("User is already approved.")
            return await callback.answer("Duplicate approval.", show_alert=True)

        logger.warning("APPROVE: owner=%s target=%s perms=%s", callback.from_user.id, target_id, ",".join(perms))
        perm_lines = "\n".join([f"- {p}" for p in perms])
        await callback.message.edit_text(
            "User Approved Successfully\n\n"
            f"User: {session.get('target_label', target_id)}\n"
            f"ID: {target_id}\n"
            "Permissions:\n"
            f"{perm_lines}"
        )
        return await callback.answer("Saved")


@Client.on_message(filters.command("approved") & (filters.private | filters.group | filters.channel))
@error_handler
async def approved_command(client: Client, message: Message):
    """Owner-only: list approved users with count."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    rows = await list_approved_users(limit=2000)
    if not rows:
        return await message.reply_text("No approved users found.", quote=True)

    lines = [f"Approved Users List ({len(rows)})", ""]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. {row.get('user_id', 0)}")

    await message.reply_text("\n".join(lines), quote=True)


@Client.on_message(filters.command(["disapprove", "unapprove"]) & (filters.private | filters.group | filters.channel))
@error_handler
async def disapprove_command(client: Client, message: Message):
    """Owner-only: revoke global approval."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/disapprove <user_id|@username>` or reply to user.", quote=True)

    if target_id == OWNER_ID:
        return await message.reply_text("Owner cannot be disapproved.", quote=True)

    ok = await disapprove_user(target_id)
    if not ok:
        return await message.reply_text("User is not approved.", quote=True)

    logger.warning("DISAPPROVE: owner=%s target=%s", message.from_user.id, target_id)
    await message.reply_text(
        "User Disapproved Successfully\n\n"
        f"User: {target_label or target_id}\n"
        f"ID: {target_id}",
        quote=True,
    )


@Client.on_message(filters.command("permissions") & (filters.private | filters.group | filters.channel))
@error_handler
async def permissions_command(client: Client, message: Message):
    """Owner-only: view one approved user's permission set."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/permissions <user_id|@username>`", quote=True)

    rows = await list_approved_users(limit=5000)
    row = next((r for r in rows if int(r.get("user_id", 0)) == int(target_id)), None)
    if not row:
        return await message.reply_text("User is not approved.", quote=True)

    perms = row.get("permissions", []) or []
    if not perms:
        return await message.reply_text(f"{target_label or target_id} has no assigned permissions.", quote=True)

    text = "\n".join([f"- {p}" for p in perms])
    await message.reply_text(
        f"Permissions for {target_label or target_id} ({target_id}):\n{text}",
        quote=True,
    )


@Client.on_message(filters.command("permkeys") & (filters.private | filters.group | filters.channel))
@error_handler
async def permkeys_command(client: Client, message: Message):
    """Owner/sudo: show all available permission keys."""
    if not message.from_user or not await is_approved_user(message.from_user.id):
        return await message.reply_text("You are not authorized to use this command.", quote=True)
    lines = ["Available Permission Keys:", ""]
    lines.extend([f"- {k}" for k in AVAILABLE_PERMISSIONS])
    await message.reply_text("\n".join(lines), quote=True)


@Client.on_message(filters.command("setperm") & (filters.private | filters.group | filters.channel))
@error_handler
async def setperm_command(client: Client, message: Message):
    """
    Owner-only: replace permissions for an approved user.
    Usage: /setperm <user_id|@username> <perm1,perm2,...>
    """
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/setperm <user_id|@username> <perm1,perm2,...>`", quote=True)
    if target_id == OWNER_ID:
        return await message.reply_text("Owner permissions cannot be edited.", quote=True)
    if len(message.command) < 3:
        return await message.reply_text("Provide at least one permission key.", quote=True)

    raw = message.text.split(None, 2)[2]
    perms = _parse_permission_args(raw)
    if not perms:
        return await message.reply_text("No valid permissions found. Use /permkeys.", quote=True)

    ok = await set_permissions(target_id, perms)
    if not ok:
        return await message.reply_text("User is not approved. Use /approve first.", quote=True)

    logger.warning("SETPERM: owner=%s target=%s perms=%s", message.from_user.id, target_id, ",".join(perms))
    await message.reply_text(
        f"Permissions updated for {target_label or target_id} ({target_id})\n"
        + "\n".join([f"- {p}" for p in perms]),
        quote=True,
    )


@Client.on_message(filters.command("addperm") & (filters.private | filters.group | filters.channel))
@error_handler
async def addperm_command(client: Client, message: Message):
    """Owner-only: add permissions to an approved user."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)
    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/addperm <user_id|@username> <perm1,perm2,...>`", quote=True)
    if len(message.command) < 3:
        return await message.reply_text("Provide permission keys to add.", quote=True)

    rows = await list_approved_users(limit=5000)
    row = next((r for r in rows if int(r.get("user_id", 0)) == int(target_id)), None)
    if not row:
        return await message.reply_text("User is not approved. Use /approve first.", quote=True)
    existing = set(row.get("permissions", []) or [])
    add = set(_parse_permission_args(message.text.split(None, 2)[2]))
    if not add:
        return await message.reply_text("No valid permissions found. Use /permkeys.", quote=True)
    new_perms = sorted(existing | add)
    await set_permissions(target_id, new_perms)
    logger.warning("ADDPERM: owner=%s target=%s perms=%s", message.from_user.id, target_id, ",".join(sorted(add)))
    await message.reply_text(
        f"Permissions added for {target_label or target_id} ({target_id}).\n"
        + "\n".join([f"- {p}" for p in new_perms]),
        quote=True,
    )


@Client.on_message(filters.command("delperm") & (filters.private | filters.group | filters.channel))
@error_handler
async def delperm_command(client: Client, message: Message):
    """Owner-only: remove permissions from an approved user."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)
    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/delperm <user_id|@username> <perm1,perm2,...>`", quote=True)
    if len(message.command) < 3:
        return await message.reply_text("Provide permission keys to remove.", quote=True)

    rows = await list_approved_users(limit=5000)
    row = next((r for r in rows if int(r.get("user_id", 0)) == int(target_id)), None)
    if not row:
        return await message.reply_text("User is not approved.", quote=True)
    existing = set(row.get("permissions", []) or [])
    remove = set(_parse_permission_args(message.text.split(None, 2)[2]))
    if not remove:
        return await message.reply_text("No valid permissions found. Use /permkeys.", quote=True)
    new_perms = sorted(existing - remove)
    await set_permissions(target_id, new_perms)
    logger.warning("DELPERM: owner=%s target=%s perms=%s", message.from_user.id, target_id, ",".join(sorted(remove)))
    await message.reply_text(
        f"Permissions removed for {target_label or target_id} ({target_id}).\n"
        + ("\n".join([f"- {p}" for p in new_perms]) if new_perms else "No permissions left."),
        quote=True,
    )


@Client.on_message(filters.command("whoami") & (filters.private | filters.group | filters.channel))
@error_handler
async def whoami_command(client: Client, message: Message):
    """Show caller role and effective permissions."""
    if not message.from_user:
        return
    uid = message.from_user.id
    if uid == OWNER_ID:
        return await message.reply_text("Role: OWNER\nPermissions: ALL", quote=True)
    if await is_sudo(uid):
        return await message.reply_text("Role: STATIC_SUDO\nPermissions: ALL", quote=True)
    perms = sorted(await get_permissions(uid))
    if perms:
        return await message.reply_text("Role: APPROVED_USER\nPermissions:\n" + "\n".join([f"- {p}" for p in perms]), quote=True)
    await message.reply_text("Role: NORMAL_USER\nPermissions: NONE", quote=True)


@Client.on_message(filters.command(["makesudo", "setsudo"]) & (filters.private | filters.group | filters.channel))
@error_handler
async def makesudo_command(client: Client, message: Message):
    """Owner-only: grant full permission set to a user."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/makesudo <user_id|@username>` or reply to user.", quote=True)
    if target_id == OWNER_ID:
        return await message.reply_text("Owner already has full access.", quote=True)

    rows = await list_approved_users(limit=5000)
    exists = any(int(r.get("user_id", 0)) == int(target_id) for r in rows)
    if exists:
        await set_permissions(target_id, AVAILABLE_PERMISSIONS)
    else:
        await approve_user(
            user_id=target_id,
            approved_by=message.from_user.id,
            permissions=AVAILABLE_PERMISSIONS,
        )

    logger.warning("MAKESUDO: owner=%s target=%s", message.from_user.id, target_id)
    await message.reply_text(
        f"Full SUDO permissions granted to {target_label or target_id} ({target_id}).",
        quote=True,
    )


@Client.on_message(filters.command(["remsudo", "unsudo"]) & (filters.private | filters.group | filters.channel))
@error_handler
async def remsudo_command(client: Client, message: Message):
    """Owner-only: remove user from approved/sudo list."""
    if not message.from_user or message.from_user.id != OWNER_ID:
        return await message.reply_text("Owner only.", quote=True)

    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/remsudo <user_id|@username>` or reply to user.", quote=True)
    if target_id == OWNER_ID:
        return await message.reply_text("Owner cannot be removed.", quote=True)

    ok = await disapprove_user(target_id)
    if not ok:
        return await message.reply_text("User is not in approved/sudo list.", quote=True)

    logger.warning("REMSUDO: owner=%s target=%s", message.from_user.id, target_id)
    await message.reply_text(
        f"SUDO/approved access removed for {target_label or target_id} ({target_id}).",
        quote=True,
    )


@Client.on_message(filters.command(["giveadmin", "grantadmin"]) & filters.group)
@error_handler
@sudo_only
async def giveadmin_command(client: Client, message: Message):
    """Grant Telegram admin rights to a user in the current group."""
    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/giveadmin <user_id|@username>` or reply to user.", quote=True)

    try:
        await client.promote_chat_member(
            message.chat.id,
            target_id,
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
            ),
        )
        await message.reply_text(f"Admin granted to {target_label or target_id} ({target_id}).", quote=True)
    except Exception as e:
        await message.reply_text(f"Failed to grant admin: `{e}`", quote=True)


@Client.on_message(filters.command(["takeadmin", "revokeadmin"]) & filters.group)
@error_handler
@sudo_only
async def takeadmin_command(client: Client, message: Message):
    """Revoke Telegram admin rights from a user in the current group."""
    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/takeadmin <user_id|@username>` or reply to user.", quote=True)

    try:
        await client.promote_chat_member(
            message.chat.id,
            target_id,
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
            ),
        )
        await message.reply_text(f"Admin revoked from {target_label or target_id} ({target_id}).", quote=True)
    except Exception as e:
        await message.reply_text(f"Failed to revoke admin: `{e}`", quote=True)


@Client.on_message(filters.command("pmpermit") & (filters.private | filters.group | filters.channel))
@error_handler
@sudo_only
async def pmpermit_command(client: Client, message: Message):
    """Toggle private-message permit for non-sudo users."""
    if len(message.command) < 2:
        current = await is_pm_permitted()
        state = "ON" if current else "OFF"
        return await message.reply_text(f"PM permit is currently: `{state}`\nUse `/pmpermit on` or `/pmpermit off`.", quote=True)

    arg = message.command[1].lower()
    if arg not in {"on", "off"}:
        return await message.reply_text("Usage: `/pmpermit on|off`", quote=True)

    enabled = arg == "on"
    await set_pm_permit(enabled)
    await message.reply_text(f"PM permit set to `{arg.upper()}`.", quote=True)


@Client.on_message(filters.command("gcast") & (filters.private | filters.group | filters.channel))
@error_handler
@permission_required("broadcast")
async def gcast_command(client: Client, message: Message):
    """Global broadcast to all registered chats."""
    reply_msg = message.reply_to_message
    text = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""

    if not reply_msg and not text:
        return await message.reply_text(
            "Usage: `/gcast <message>`\nOr reply to any message with `/gcast`.",
            quote=True,
        )

    groups = await get_all_groups()
    if not groups:
        return await message.reply_text("No groups registered.", quote=True)

    status = await message.reply_text(f"Broadcasting to {len(groups)} chats...", quote=True)

    sent = 0
    failed = 0
    copy_mode = reply_msg is not None

    for chat_id in groups:
        try:
            if copy_mode:
                await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
            else:
                await client.send_message(chat_id, text)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                if copy_mode:
                    await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
                else:
                    await client.send_message(chat_id, text)
                sent += 1
            except Exception as retry_err:
                logger.warning("gcast retry failed for %s: %s", chat_id, retry_err)
                failed += 1
        except Exception as e:
            logger.warning("gcast failed for %s: %s", chat_id, e)
            failed += 1

        await asyncio.sleep(0.25)

    await status.edit_text(f"GCAST complete.\nSent: {sent}\nFailed: {failed}")


@Client.on_message(filters.command("megacast") & (filters.private | filters.group | filters.channel))
@error_handler
@permission_required("broadcast")
async def megacast_command(client: Client, message: Message):
    """
    High-throughput global broadcast with live progress.
    Supports text mode and reply-copy mode.
    """
    reply_msg = message.reply_to_message
    text = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""

    if not reply_msg and not text:
        return await message.reply_text(
            "Usage: `/megacast <message>`\nOr reply to any message with `/megacast`.",
            quote=True,
        )

    groups = await get_all_groups()
    if not groups:
        return await message.reply_text("No groups registered.", quote=True)

    status = await message.reply_text(f"MEGACAST started for {len(groups)} chats...", quote=True)
    copy_mode = reply_msg is not None

    sent = 0
    failed = 0
    done = 0
    total = len(groups)
    lock = asyncio.Lock()

    async def send_one(chat_id: int):
        nonlocal sent, failed, done
        try:
            if copy_mode:
                await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
            else:
                await client.send_message(chat_id, text)
            async with lock:
                sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                if copy_mode:
                    await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
                else:
                    await client.send_message(chat_id, text)
                async with lock:
                    sent += 1
            except Exception as retry_err:
                logger.warning("megacast retry failed for %s: %s", chat_id, retry_err)
                async with lock:
                    failed += 1
        except Exception as e:
            logger.warning("megacast failed for %s: %s", chat_id, e)
            async with lock:
                failed += 1
        finally:
            async with lock:
                done += 1

    # Controlled concurrency to keep load stable.
    batch_size = 20
    for i in range(0, total, batch_size):
        batch = groups[i : i + batch_size]
        await asyncio.gather(*[send_one(chat_id) for chat_id in batch])
        try:
            await status.edit_text(
                f"MEGACAST running...\nProgress: {done}/{total}\nSent: {sent}\nFailed: {failed}"
            )
        except Exception:
            pass

    await status.edit_text(
        f"MEGACAST complete.\nTotal: {total}\nSent: {sent}\nFailed: {failed}"
    )


@Client.on_message(filters.command("gcastpin") & (filters.private | filters.group | filters.channel))
@error_handler
@permission_required("broadcast")
async def gcastpin_command(client: Client, message: Message):
    """Global broadcast and pin in destination chats where possible."""
    reply_msg = message.reply_to_message
    text = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""

    if not reply_msg and not text:
        return await message.reply_text(
            "Usage: `/gcastpin <message>`\nOr reply to any message with `/gcastpin`.",
            quote=True,
        )

    groups = await get_all_groups()
    if not groups:
        return await message.reply_text("No groups registered.", quote=True)

    status = await message.reply_text(f"Broadcast+pin to {len(groups)} chats...", quote=True)

    sent = 0
    failed = 0
    pinned = 0
    pin_failed = 0
    copy_mode = reply_msg is not None

    for chat_id in groups:
        try:
            if copy_mode:
                out = await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
            else:
                out = await client.send_message(chat_id, text)
            sent += 1
            try:
                await client.pin_chat_message(chat_id=chat_id, message_id=out.id, disable_notification=True)
                pinned += 1
            except Exception:
                pin_failed += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                if copy_mode:
                    out = await client.copy_message(chat_id=chat_id, from_chat_id=reply_msg.chat.id, message_id=reply_msg.id)
                else:
                    out = await client.send_message(chat_id, text)
                sent += 1
                try:
                    await client.pin_chat_message(chat_id=chat_id, message_id=out.id, disable_notification=True)
                    pinned += 1
                except Exception:
                    pin_failed += 1
            except Exception as retry_err:
                logger.warning("gcastpin retry failed for %s: %s", chat_id, retry_err)
                failed += 1
        except Exception as e:
            logger.warning("gcastpin failed for %s: %s", chat_id, e)
            failed += 1

        await asyncio.sleep(0.25)

    await status.edit_text(
        f"GCAST+PIN complete.\nSent: {sent}\nFailed: {failed}\nPinned: {pinned}\nPin Failed: {pin_failed}"
    )


@Client.on_message(filters.command("stormban") & (filters.private | filters.group | filters.channel))
@error_handler
@permission_required("ban")
async def stormban_command(client: Client, message: Message):
    """Ban a target user across all registered groups with summary report."""
    target_id, target_label = await _resolve_target_user(client, message)
    if not target_id:
        return await message.reply_text("Usage: `/stormban <user_id|@username> [reason]` or reply to user.", quote=True)
    if target_id == OWNER_ID:
        return await message.reply_text("Cannot stormban owner.", quote=True)

    # Parse reason
    reason = "No reason"
    if message.reply_to_message:
        reason = " ".join(message.command[1:]).strip() or "No reason"
    elif len(message.command) > 2:
        reason = " ".join(message.command[2:]).strip() or "No reason"

    groups = await get_all_groups()
    if not groups:
        return await message.reply_text("No groups registered.", quote=True)

    status = await message.reply_text(f"STORMBAN started for `{target_id}` in {len(groups)} groups...", quote=True)
    banned = 0
    failed = 0

    for i, chat_id in enumerate(groups, start=1):
        try:
            await client.ban_chat_member(chat_id, target_id)
            banned += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await client.ban_chat_member(chat_id, target_id)
                banned += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if i % 100 == 0:
            try:
                await status.edit_text(
                    f"STORMBAN running...\nProgress: {i}/{len(groups)}\nBanned: {banned}\nFailed: {failed}"
                )
            except Exception:
                pass

    logger.warning("STORMBAN by %s target=%s reason=%s", message.from_user.id if message.from_user else 0, target_id, reason)
    await status.edit_text(
        "STORMBAN complete.\n"
        f"Target: {target_label or target_id} ({target_id})\n"
        f"Reason: {reason}\n"
        f"Success: {banned}\n"
        f"Failed: {failed}"
    )


@Client.on_message(filters.command("userbotleaveall") & (filters.private | filters.group | filters.channel))
@error_handler
@sudo_only
async def userbotleaveall_command(client: Client, message: Message):
    """Make assistant userbot leave all registered chats."""
    from core.assistant import assistant

    groups = await get_all_groups()
    if not groups:
        return await message.reply_text("No groups registered.", quote=True)

    status = await message.reply_text(f"Userbot leaving {len(groups)} chats...", quote=True)

    left = 0
    failed = 0
    for chat_id in groups:
        try:
            await assistant.leave_chat(chat_id)
            left += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await assistant.leave_chat(chat_id)
                left += 1
            except Exception as retry_err:
                logger.warning("userbotleaveall retry failed for %s: %s", chat_id, retry_err)
                failed += 1
        except Exception as e:
            logger.debug("userbotleaveall failed for %s: %s", chat_id, e)
            failed += 1

        await asyncio.sleep(0.15)

    await status.edit_text(f"Userbot leave-all complete.\nLeft: {left}\nFailed: {failed}")


@Client.on_message(filters.command("nukechat") & filters.group)
@error_handler
@permission_required("mute")
async def nukechat_command(client: Client, message: Message):
    """Delete last N messages from current chat quickly."""
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/nukechat <count>` (max 1000)", quote=True)

    try:
        count = int(message.command[1])
    except ValueError:
        return await message.reply_text("Count must be a number.", quote=True)

    count = max(1, min(count, 1000))
    status = await message.reply_text(f"Nuking last {count} messages...", quote=True)

    msg_ids = []
    async for m in client.get_chat_history(message.chat.id, limit=count):
        msg_ids.append(m.id)

    deleted = 0
    for i in range(0, len(msg_ids), 100):
        batch = msg_ids[i : i + 100]
        try:
            await client.delete_messages(message.chat.id, batch)
            deleted += len(batch)
        except Exception:
            # fallback single delete for partial failures
            for mid in batch:
                try:
                    await client.delete_messages(message.chat.id, mid)
                    deleted += 1
                except Exception:
                    pass

    await status.edit_text(f"NUKE complete.\nRequested: {count}\nDeleted: {deleted}")


@Client.on_message(filters.command("massmute") & filters.group)
@error_handler
@permission_required("mute")
async def massmute_command(client: Client, message: Message):
    """Mute non-admin members in current chat. Usage: /massmute <minutes> [limit]."""
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/massmute <minutes> [limit]`", quote=True)

    try:
        minutes = int(message.command[1])
    except ValueError:
        return await message.reply_text("Minutes must be a number.", quote=True)
    minutes = max(1, min(minutes, 1440))

    limit = 300
    if len(message.command) > 2:
        try:
            limit = int(message.command[2])
        except ValueError:
            pass
    limit = max(10, min(limit, 3000))

    status = await message.reply_text(
        f"MASSMUTE started.\nDuration: {minutes}m\nScan limit: {limit}",
        quote=True,
    )

    # Gather admin IDs to skip.
    admin_ids = set()
    async for admin in client.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
        if admin.user:
            admin_ids.add(admin.user.id)
    if message.from_user:
        admin_ids.add(message.from_user.id)
    admin_ids.add(OWNER_ID)

    muted = 0
    failed = 0
    scanned = 0
    until_ts = int(time.time()) + (minutes * 60)

    async for member in client.get_chat_members(message.chat.id):
        if scanned >= limit:
            break
        scanned += 1

        user = member.user
        if not user or user.is_bot or user.id in admin_ids:
            continue
        try:
            await client.restrict_chat_member(
                message.chat.id,
                user.id,
                permissions=ChatPermissions(),
                until_date=until_ts,
            )
            muted += 1
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await client.restrict_chat_member(
                    message.chat.id,
                    user.id,
                    permissions=ChatPermissions(),
                    until_date=until_ts,
                )
                muted += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        if scanned % 100 == 0:
            try:
                await status.edit_text(
                    f"MASSMUTE running...\nScanned: {scanned}/{limit}\nMuted: {muted}\nFailed: {failed}"
                )
            except Exception:
                pass

    await status.edit_text(
        f"MASSMUTE complete.\nScanned: {scanned}\nMuted: {muted}\nFailed: {failed}\nDuration: {minutes}m"
    )


def _warroom_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Restart", callback_data="wr:restart"),
                InlineKeyboardButton("Stats", callback_data="wr:stats"),
            ],
            [
                InlineKeyboardButton("Maint ON", callback_data="wr:maint_on"),
                InlineKeyboardButton("Maint OFF", callback_data="wr:maint_off"),
            ],
            [
                InlineKeyboardButton("LeaveAll", callback_data="wr:leaveall"),
                InlineKeyboardButton("Cleanup", callback_data="wr:cleanup"),
            ],
            [InlineKeyboardButton("Close", callback_data="wr:close")],
        ]
    )


@Client.on_message(filters.command("warroom") & (filters.private | filters.group | filters.channel))
@error_handler
async def warroom_command(client: Client, message: Message):
    """Open power-control panel for approved operators."""
    if not message.from_user or not await is_approved_user(message.from_user.id):
        return await message.reply_text("You are not authorized to use this command.", quote=True)

    text = (
        "WARROOM\n"
        "High-power control panel.\n"
        "Use carefully."
    )
    sent = await message.reply_text(text, quote=True, reply_markup=_warroom_markup())
    warroom_sessions[sent.id] = {"owner_id": message.from_user.id, "expires_at": time.time() + 900}


@Client.on_callback_query(filters.regex(r"^wr:(restart|stats|maint_on|maint_off|leaveall|cleanup|close)$"))
async def warroom_callback(client: Client, callback: CallbackQuery):
    if not callback.from_user:
        return await callback.answer("Unknown user.", show_alert=True)

    wr = _get_warroom(callback.message.id)
    if not wr:
        return await callback.answer("Warroom expired.", show_alert=True)
    if callback.from_user.id not in {wr.get("owner_id"), OWNER_ID}:
        return await callback.answer("Not your warroom panel.", show_alert=True)

    action = callback.data.split(":", 1)[1]

    if action == "close":
        warroom_sessions.pop(callback.message.id, None)
        try:
            await callback.message.delete()
        except Exception:
            pass
        return await callback.answer("Closed")

    if action == "stats":
        if not await has_permission(callback.from_user.id, "stats"):
            return await callback.answer("No stats permission.", show_alert=True)
        from utils.queue import active_queue_count
        from utils.resource_guard import get_resource_stats

        res = get_resource_stats()
        groups = await get_all_groups()
        text = (
            "WARROOM STATS\n"
            f"CPU: {res.get('cpu', 0)}%\n"
            f"RAM: {res.get('ram_percent', 0)}%\n"
            f"Active Queues: {active_queue_count()}\n"
            f"Registered Chats: {len(groups)}"
        )
        await callback.message.edit_text(text, reply_markup=_warroom_markup())
        return await callback.answer("Updated")

    if action in {"maint_on", "maint_off"}:
        if not await is_sudo(callback.from_user.id):
            return await callback.answer("Only owner/static sudo can toggle maintenance.", show_alert=True)
        from core.maintenance import set_maintenance

        await set_maintenance(action == "maint_on")
        await callback.answer("Maintenance updated")
        return

    if action == "leaveall":
        if not await is_sudo(callback.from_user.id):
            return await callback.answer("Only owner/static sudo can run leaveall.", show_alert=True)
        from core.assistant import assistant

        groups = await get_all_groups()
        left = 0
        for chat_id in groups:
            try:
                await assistant.leave_chat(chat_id)
                left += 1
            except Exception:
                pass
        await callback.answer(f"LeaveAll done: {left}", show_alert=True)
        return

    if action == "cleanup":
        if not await is_sudo(callback.from_user.id):
            return await callback.answer("Only owner/static sudo can run cleanup.", show_alert=True)
        from utils.stream import cleanup_all
        from utils.queue import _queues

        await cleanup_all()
        _queues.clear()
        await callback.answer("Cleanup complete.", show_alert=True)
        return

    if action == "restart":
        if not await has_permission(callback.from_user.id, "restart"):
            return await callback.answer("No restart permission.", show_alert=True)

        await callback.answer("Restarting...", show_alert=True)
        from core.call import call_manager
        from core.assistant import assistant
        from core.voice_cleanup import stop_cleanup
        from utils.stream import cleanup_all

        stop_cleanup()
        for cid in list(call_manager._calls):
            try:
                gc = call_manager._calls[cid]
                gc.stop_playout()
                await gc.leave_current_group_call()
            except Exception:
                pass
        await cleanup_all()
        try:
            await assistant.stop()
        except Exception:
            pass
        try:
            await client.stop()
        except Exception:
            pass
        await asyncio.sleep(2)
        os.execv(sys.executable, [sys.executable, "main.py"])

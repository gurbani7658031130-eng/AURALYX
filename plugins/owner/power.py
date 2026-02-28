"""
Auralyx Music — Owner: Power Tools
/o_userinfo, /o_chatinfo, /o_set_daily, /o_set_robrate,
/o_globalannounce, /o_backup, /o_shell, /o_addsudo, /o_removesudo
"""

import os
import sys
import json
import time
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import owner_only, error_handler, owner_rate_limit
from database.mongo import (
    get_user_economy, get_all_groups, economy_col,
    set_dynamic_config, get_dynamic_config,
)
from config import LOG_CHANNEL_ID, SUDO_USERS

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("o_userinfo") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_userinfo(client: Client, message: Message):
    """Full dump of a user's data."""
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) >= 2:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("• Invalid user ID.", quote=True)
            return
    else:
        await message.reply_text("• Reply or provide user ID.", quote=True)
        return

    doc = await get_user_economy(target_id)

    # Try to get Telegram info
    try:
        user = await client.get_users(target_id)
        tg_info = (
            f"  Name: **{user.first_name}** {user.last_name or ''}\n"
            f"  Username: @{user.username or 'None'}\n"
            f"  Premium: `{user.is_premium}`\n"
        )
    except Exception:
        tg_info = f"  _Could not fetch Telegram info._\n"

    # Format economy data
    wallet = doc.get("wallet", 0)
    bank = doc.get("bank", 0)
    kills = doc.get("kills", 0)
    deaths = doc.get("deaths", 0)
    level = doc.get("level", 1)
    xp = doc.get("xp", 0)
    vip = doc.get("vip_level", 0)
    streak = doc.get("streak", 0)
    title = doc.get("custom_title", "")
    partner = doc.get("partner_id", 0)
    inventory = doc.get("inventory", [])
    games_w = doc.get("games_won", 0)
    games_l = doc.get("games_lost", 0)

    is_sudo = target_id in SUDO_USERS
    from core.shadowban import is_shadowbanned
    is_shadow = is_shadowbanned(target_id)
    from database.mongo import is_gbanned
    is_gb = await is_gbanned(target_id)

    await message.reply_text(
        f"🔍 **USER INFO** — `{target_id}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"**Telegram:**\n{tg_info}"
        f"\n**Economy:**\n"
        f"  Wallet: `{wallet:,}` | Bank: `{bank:,}`\n"
        f"  Net: `{wallet + bank:,}`\n"
        f"  Level: `{level}` (XP: {xp})\n"
        f"  Streak: `{streak}` | VIP: `{vip}`\n"
        f"  Title: `{title or 'None'}`\n"
        f"\n**Combat:**\n"
        f"  Kills: `{kills}` | Deaths: `{deaths}`\n"
        f"  Games: `{games_w}W/{games_l}L`\n"
        f"\n**Status:**\n"
        f"  Sudo: `{is_sudo}` | Shadow: `{is_shadow}` | GBan: `{is_gb}`\n"
        f"  Partner: `{partner or 'None'}`\n"
        f"  Items: `{len(inventory)}`\n"
        f"━━━━━━━━━━━━━━━━━━",
        quote=True,
    )


@Client.on_message(filters.command("o_chatinfo") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_chatinfo(client: Client, message: Message):
    """Full dump of a group's data."""
    if len(message.command) < 2:
        if message.chat.type in ("group", "supergroup"):
            chat_id = message.chat.id
        else:
            await message.reply_text("• Usage: `/o_chatinfo <chat_id>`", quote=True)
            return
    else:
        try:
            chat_id = int(message.command[1])
        except ValueError:
            await message.reply_text("• Invalid chat ID.", quote=True)
            return

    try:
        chat = await client.get_chat(chat_id)
        await message.reply_text(
            f"🔍 **CHAT INFO** — `{chat_id}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"  Title: **{chat.title}**\n"
            f"  Type: `{chat.type}`\n"
            f"  Members: `{chat.members_count or '?'}`\n"
            f"  Username: @{chat.username or 'None'}\n"
            f"  ID: `{chat.id}`\n"
            f"━━━━━━━━━━━━━━━━━━",
            quote=True,
        )
    except Exception as e:
        await message.reply_text(f"• Failed: `{e}`", quote=True)


@Client.on_message(filters.command("o_set_daily") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_set_daily(client: Client, message: Message):
    """Change daily reward amount at runtime."""
    if len(message.command) < 2:
        current = await get_dynamic_config("daily_reward", 500)
        await message.reply_text(f"• Current daily reward: `{current}`\n• `/o_set_daily <amount>`", quote=True)
        return

    try:
        amount = int(message.command[1])
    except ValueError:
        await message.reply_text("• Must be a number.", quote=True)
        return

    await set_dynamic_config("daily_reward", amount)
    await message.reply_text(f"✅ Daily reward set to **{amount:,}** coins.", quote=True)


@Client.on_message(filters.command("o_set_robrate") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_set_robrate(client: Client, message: Message):
    """Change rob success rate at runtime (0.0-1.0)."""
    if len(message.command) < 2:
        current = await get_dynamic_config("rob_rate", 0.4)
        await message.reply_text(f"• Current rob rate: `{current}`\n• `/o_set_robrate <0.0-1.0>`", quote=True)
        return

    try:
        rate = float(message.command[1])
        if not 0.0 <= rate <= 1.0:
            raise ValueError
    except ValueError:
        await message.reply_text("• Must be between 0.0 and 1.0.", quote=True)
        return

    await set_dynamic_config("rob_rate", rate)
    await message.reply_text(f"✅ Rob success rate set to **{rate:.0%}**.", quote=True)


@Client.on_message(filters.command("o_globalannounce") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(30)
@error_handler
async def owner_globalannounce(client: Client, message: Message):
    """Broadcast to all groups with optional pin."""
    if len(message.command) < 2 and not message.reply_to_message:
        await message.reply_text("• Usage: `/o_globalannounce <message>`", quote=True)
        return

    if message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption or ""
    else:
        text = " ".join(message.command[1:])

    groups = await get_all_groups()
    status = await message.reply_text(f"📢 Broadcasting to **{len(groups)}** groups...", quote=True)

    sent, failed, pinned = 0, 0, 0
    for chat_id in groups:
        try:
            msg = await client.send_message(
                chat_id,
                f"📢 **GLOBAL ANNOUNCEMENT**\n━━━━━━━━━━━━━━\n{text}\n━━━━━━━━━━━━━━",
            )
            sent += 1
            try:
                await msg.pin(disable_notification=True)
                pinned += 1
            except Exception:
                pass
        except Exception:
            failed += 1
        await asyncio.sleep(0.3)

    await status.edit_text(
        f"📢 **Broadcast Complete!**\n"
        f"✅ Sent: **{sent}** | ❌ Failed: **{failed}** | 📌 Pinned: **{pinned}**"
    )


@Client.on_message(filters.command("o_backup") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(60)
@error_handler
async def owner_backup(client: Client, message: Message):
    """Export economy data to JSON file."""
    msg = await message.reply_text("📦 Creating backup...", quote=True)

    cursor = economy_col.find({})
    data = []
    async for doc in cursor:
        doc.pop("_id", None)
        data.append(doc)

    filename = f"economy_backup_{int(time.time())}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    await client.send_document(
        message.chat.id, filename,
        caption=f"📦 **Economy Backup**\n• Records: **{len(data)}**\n• File: `{filename}`"
    )
    os.remove(filename)
    await msg.delete()


@Client.on_message(filters.command("o_shell") & (filters.private | filters.group))
@owner_only
@owner_rate_limit(5)
@error_handler
async def owner_shell(client: Client, message: Message):
    """Execute a shell command. DANGEROUS — owner only."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/o_shell <command>`", quote=True)
        return

    cmd = message.text.split(None, 1)[1]

    # Log for security
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(
                LOG_CHANNEL_ID,
                f"🔴 **SHELL EXECUTED**\n"
                f"👤 Owner: `{message.from_user.id}`\n"
                f"📝 Command: `{cmd}`"
            )
        except Exception:
            pass

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")

        if not output.strip():
            output = "_No output_"
        elif len(output) > 3800:
            output = output[:3800] + "\n... _truncated_"

        await message.reply_text(f"```\n{output}\n```", quote=True)
    except asyncio.TimeoutError:
        await message.reply_text("• Command timed out (15s).", quote=True)
    except Exception as e:
        await message.reply_text(f"• Error: `{e}`", quote=True)


@Client.on_message(filters.command("o_addsudo") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_addsudo(client: Client, message: Message):
    """Add a sudo user at runtime."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/o_addsudo <user_id>`", quote=True)
        return

    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply_text("• Invalid user ID.", quote=True)
        return

    if user_id in SUDO_USERS:
        await message.reply_text("• User is already SUDO.", quote=True)
        return

    SUDO_USERS.add(user_id)
    await message.reply_text(f"✅ **Added SUDO:** `{user_id}`\n⚠️ Runtime only — add to `.env` for persistence.", quote=True)
    logger.warning("OWNER added SUDO: %s", user_id)


@Client.on_message(filters.command("o_removesudo") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_removesudo(client: Client, message: Message):
    """Remove a sudo user at runtime."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/o_removesudo <user_id>`", quote=True)
        return

    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply_text("• Invalid user ID.", quote=True)
        return

    if user_id not in SUDO_USERS:
        await message.reply_text("• User is not SUDO.", quote=True)
        return

    SUDO_USERS.discard(user_id)
    await message.reply_text(f"✅ **Removed SUDO:** `{user_id}`\n⚠️ Runtime only — update `.env` for persistence.", quote=True)
    logger.warning("OWNER removed SUDO: %s", user_id)

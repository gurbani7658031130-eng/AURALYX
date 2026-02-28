"""
Auralyx Music - Start Panel / Help UI
"""

import logging
import os
import time

import psutil
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import OWNER_ID
from database.mongo import add_group, add_user, get_stat, get_total_groups, get_total_users

logger = logging.getLogger(__name__)

START_TIME = time.time()


def _format_uptime() -> str:
    delta = int(time.time() - START_TIME)
    days, rem = divmod(delta, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m {seconds}s"


def _base_panel(title: str, body: str) -> str:
    return (
        f"**{title}**\n"
        "`━━━━━━━━━━━━━━━━━━━━━━━━`\n"
        f"{body}\n"
        "`━━━━━━━━━━━━━━━━━━━━━━━━`"
    )


def _home_text(first_name: str, username: str) -> str:
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    body = (
        f"Welcome, **{first_name}**\n"
        f"Bot: **@{username}**\n"
        f"Uptime: `{_format_uptime()}`\n"
        f"Load: `CPU {cpu}% • RAM {ram}%`\n\n"
        "Tap the panel buttons below for quick navigation."
    )
    return _base_panel("AURALYX MUSIC CONTROL CENTER", body)


async def _stats_text() -> str:
    users = await get_total_users()
    groups = await get_total_groups()
    plays = await get_stat("total_plays")
    res = {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
    }
    body = (
        f"Users: `{users}`\n"
        f"Groups: `{groups}`\n"
        f"Total Plays: `{plays}`\n"
        f"Uptime: `{_format_uptime()}`\n"
        f"CPU/RAM: `{res['cpu']}% / {res['ram']}%`"
    )
    return _base_panel("SYSTEM STATS", body)


def _music_text() -> str:
    body = (
        "**Core Playback**\n"
        "`/play <query>` : Start audio stream\n"
        "`/vplay <query>` : Start video stream\n"
        "`/pause` : Pause current stream\n"
        "`/resume` : Resume paused stream\n"
        "`/skip` : Play next queued track\n"
        "`/stop` : Stop stream and clear VC\n\n"
        "**Queue Controls**\n"
        "`/queue` : Show queued tracks\n"
        "`/nowplaying` : Current track info\n"
        "`/replay` : Replay current track\n"
        "`/loop off|track|queue` : Set loop mode\n"
        "`/shuffle` : Shuffle queue\n"
        "`/remove <position>` : Remove one queued item\n"
        "`/clear` : Clear queued items\n\n"
        "**Discovery**\n"
        "`/search <query>` : Show top song results\n"
        "`/vsearch <query>` : Show top video results\n"
        "`/playlist save|play|list|delete` : Manage playlists\n"
        "`/history` : Last played tracks\n"
        "`/toptracks` : Most played tracks\n"
        "`/autoplay on|off` : Auto-pick next track\n"
        "`/lyrics <song>` : Fetch lyrics"
    )
    return _base_panel("MUSIC PANEL", body)


def _admin_text() -> str:
    body = (
        "**Moderation**\n"
        "`/mute <user>` : Mute target user\n"
        "`/unmute <user>` : Unmute target user\n"
        "`/ban <user>` : Ban target user\n"
        "`/unban <user>` : Unban target user\n"
        "`/kick <user>` : Kick target user\n"
        "`/purge <count>` : Delete recent messages\n\n"
        "**Admin Actions**\n"
        "`/promote` (reply) : Grant admin rights\n"
        "`/demote` (reply) : Remove admin rights\n"
        "`/pin` (reply) : Pin a message\n"
        "`/unpin` : Unpin message/all pins\n"
        "`/warn` : Warn a user\n"
        "`/unwarn` : Remove one warning\n"
        "`/warnings` : Show warning count\n\n"
        "**Utilities**\n"
        "`/getid` : Extract custom emoji IDs\n"
        "`/ping` : Bot response latency\n"
        "`/stats` : Bot statistics"
    )
    return _base_panel("ADMIN PANEL", body)


def _power_text() -> str:
    body = (
        "**Approval System**\n"
        "`/approve <user>` : Open permission panel\n"
        "`/approved` : List approved users\n"
        "`/disapprove <user>` : Remove approval\n"
        "`/permissions <user>` : View assigned permissions\n"
        "`/setperm <user> <keys>` : Replace permissions\n"
        "`/addperm <user> <keys>` : Add permissions\n"
        "`/delperm <user> <keys>` : Remove permissions\n"
        "`/permkeys` : Show valid permission keys\n\n"
        "**Global Ops**\n"
        "`/gcast` : Global broadcast\n"
        "`/gcastpin` : Global broadcast + pin\n"
        "`/megacast` : High-throughput broadcast\n"
        "`/stormban <user>` : Ban user in all chats\n"
        "`/nukechat <count>` : Fast chat cleanup\n"
        "`/massmute <min> [limit]` : Bulk temporary mute\n\n"
        "**Autonomous Ops**\n"
        "`/autoclean on|off [ttl]` : Auto-delete commands\n"
        "`/autowarn on|off [n] [sec]` : Spam auto-warning\n"
        "`/safeurl on|off` : Block suspicious URLs\n"
        "`/backupauto on|off` : Scheduled backups\n"
        "`/autobroadcast on|off|now` : Scheduled global announce\n"
        "`/incident` : Emergency action panel\n"
        "`/warroom` : Live power control panel\n"
        "`/selftest` : Runtime diagnostics"
    )
    return _base_panel("POWER OPS PANEL", body)


def _home_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("Add to Group", url="https://t.me/AuralyxXMusicBot?startgroup=true"),
            InlineKeyboardButton("Updates", url="https://t.me/AuralyxUpdates"),
        ],
        [
            InlineKeyboardButton("Music", callback_data="panel_music"),
            InlineKeyboardButton("Admin", callback_data="panel_admin"),
            InlineKeyboardButton("Power", callback_data="panel_power"),
        ],
        [
            InlineKeyboardButton("Stats", callback_data="panel_stats"),
            InlineKeyboardButton("Help", callback_data="panel_help"),
        ],
        [InlineKeyboardButton("Support", url="https://t.me/AuralyxSupport")],
    ]
    if user_id == OWNER_ID:
        rows.append([InlineKeyboardButton("Master", callback_data="panel_master")])
    return InlineKeyboardMarkup(rows)


def _sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="panel_home")]])


@Client.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user = message.from_user
    try:
        if user:
            await add_user(user.id, user.first_name or "Unknown")
        if message.chat and message.chat.id < 0:
            await add_group(message.chat.id, message.chat.title or "Unknown")
    except Exception:
        pass

    text = _home_text(user.first_name if user else "there", client.me.username)
    markup = _home_keyboard(user.id if user else 0)
    photo_path = "Start_Panel.png"

    if os.path.exists(photo_path):
        await message.reply_photo(photo=photo_path, caption=text, reply_markup=markup, quote=True)
    else:
        await message.reply_text(text, reply_markup=markup, quote=True)


@Client.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    await message.reply_text(_music_text(), quote=True, reply_markup=_sub_keyboard())


@Client.on_message(filters.new_chat_members)
async def bot_added_to_group(client: Client, message: Message):
    if any(m.is_self for m in message.new_chat_members):
        text = _base_panel(
            "AURALYX MUSIC ONLINE",
            "Use `/play` to start music\nUse `/start` to open full panel",
        )
        markup = _home_keyboard(message.from_user.id if message.from_user else 0)
        photo_path = "Start_Panel.png"
        if os.path.exists(photo_path):
            await message.reply_photo(photo=photo_path, caption=text, reply_markup=markup)
        else:
            await message.reply_text(text, reply_markup=markup)


@Client.on_callback_query(filters.regex(r"^panel_(home|music|admin|power|stats|help|master)$"))
async def panel_callback(client: Client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id

    if data == "panel_home":
        text = _home_text(callback.from_user.first_name, client.me.username)
        markup = _home_keyboard(user_id)
    elif data == "panel_music":
        text = _music_text()
        markup = _sub_keyboard()
    elif data == "panel_admin":
        text = _admin_text()
        markup = _sub_keyboard()
    elif data == "panel_power":
        text = _power_text()
        markup = _sub_keyboard()
    elif data == "panel_stats":
        text = await _stats_text()
        markup = _sub_keyboard()
    elif data == "panel_help":
        text = _base_panel("HELP", "Use panel tabs for sections.\nUse `/start` anytime to reopen this panel.")
        markup = _sub_keyboard()
    else:
        if user_id != OWNER_ID:
            return await callback.answer("Not authorized.", show_alert=True)
        text = _base_panel("MASTER", "Owner shortcuts are enabled.\nUse `/warroom` for live operations.")
        markup = _sub_keyboard()

    await callback.answer()
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await callback.message.edit_text(text=text, reply_markup=markup)
    except Exception:
        pass

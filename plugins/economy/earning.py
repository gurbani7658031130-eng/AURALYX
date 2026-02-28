"""
Auralyx Music — Economy: Earning
/work, /crime, /beg, /fish, /hunt
"""

import random
import time
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from utils.cooldown import cooldown
from database.mongo import update_wallet, add_xp, get_user_economy

logger = logging.getLogger(__name__)


# ── Job descriptions ──
_WORK_JOBS = [
    ("🧑‍💻 Programming", 150, 500),
    ("🍳 Cooking at a restaurant", 100, 350),
    ("📦 Delivering packages", 120, 400),
    ("🧹 Cleaning offices", 80, 250),
    ("🎨 Painting a mural", 200, 600),
    ("🔧 Fixing cars", 150, 450),
    ("📸 Photography gig", 180, 550),
    ("🎶 Street performing", 100, 400),
    ("🏗️ Construction work", 200, 650),
    ("✂️ Hairdressing", 100, 300),
    ("🛒 Cashier shift", 80, 200),
    ("🧪 Lab research", 250, 700),
]

_CRIME_SCENARIOS = [
    ("🏦 Robbed a bank", 500, 2000, 0.4),
    ("💎 Stole jewelry", 300, 1500, 0.45),
    ("🎰 Rigged a slot machine", 400, 1800, 0.35),
    ("📱 Hacked a phone", 200, 1000, 0.5),
    ("🚗 Grand theft auto", 600, 2500, 0.3),
    ("💼 Embezzled funds", 800, 3000, 0.25),
]

_BEG_RESPONSES = [
    ("A stranger gave you some coins", 10, 100),
    ("Someone felt generous", 20, 150),
    ("A kind soul donated", 5, 80),
    ("You found coins on the ground", 1, 50),
    ("A wealthy person tipped you", 50, 200),
    ("Nobody cared", 0, 0),
    ("Someone threw a coin at you", 1, 30),
]

_FISH = [
    ("🐟 Sardine", 10, 50),
    ("🐠 Clownfish", 30, 100),
    ("🐡 Pufferfish", 50, 150),
    ("🦈 Shark", 200, 500),
    ("🐙 Octopus", 100, 300),
    ("🐚 Seashell", 5, 20),
    ("🗑️ Old boot", 0, 0),
    ("🐋 Whale", 500, 1000),
    ("🦞 Lobster", 150, 400),
]

_HUNT = [
    ("🐰 Rabbit", 20, 80),
    ("🦌 Deer", 100, 300),
    ("🐗 Wild Boar", 80, 250),
    ("🦅 Eagle", 150, 400),
    ("🐻 Bear", 200, 600),
    ("🦊 Fox", 60, 200),
    ("🐿️ Squirrel", 10, 40),
    ("🦁 Lion", 500, 1200),
    ("Nothing... you came back empty", 0, 0),
]


@Client.on_message(filters.command("work") & filters.group)
@error_handler
@rate_limit(3)
async def work_command(client: Client, message: Message):
    """Work a random job for coins. 30min cooldown."""
    user_id = message.from_user.id
    allowed, remaining = cooldown.check(user_id, "work", 1800)
    if not allowed:
        mins = remaining // 60
        secs = remaining % 60
        await message.reply_text(f"⏳ You're tired! Rest for `{mins}m {secs}s`.", quote=True)
        return

    job, min_pay, max_pay = random.choice(_WORK_JOBS)
    earned = random.randint(min_pay, max_pay)
    await update_wallet(user_id, earned)
    xp_result = await add_xp(user_id, 10)

    text = (
        f"💼 **WORK COMPLETE!**\n"
        f"━━━━━━━━━━━━━━\n"
        f"{job}\n"
        f"💰 Earned: **{earned:,}** coins\n"
        f"✨ +10 XP\n"
        f"━━━━━━━━━━━━━━"
    )
    if xp_result["leveled_up"]:
        text += f"\n\n🎉 **LEVEL UP!** → Level **{xp_result['new_level']}**"

    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("crime") & filters.group)
@error_handler
@rate_limit(3)
async def crime_command(client: Client, message: Message):
    """High risk/reward crime. 1hr cooldown. Can lose coins on failure."""
    user_id = message.from_user.id
    allowed, remaining = cooldown.check(user_id, "crime", 3600)
    if not allowed:
        mins = remaining // 60
        await message.reply_text(f"⏳ Lay low for `{mins}m`.", quote=True)
        return

    scenario, min_pay, max_pay, success_rate = random.choice(_CRIME_SCENARIOS)

    if random.random() < success_rate:
        earned = random.randint(min_pay, max_pay)
        await update_wallet(user_id, earned)
        xp_result = await add_xp(user_id, 25)
        text = (
            f"🔫 **CRIME SUCCESSFUL!**\n"
            f"━━━━━━━━━━━━━━\n"
            f"{scenario}\n"
            f"💰 Loot: **{earned:,}** coins\n"
            f"✨ +25 XP\n"
            f"━━━━━━━━━━━━━━"
        )
        if xp_result["leveled_up"]:
            text += f"\n\n🎉 **LEVEL UP!** → Level **{xp_result['new_level']}**"
    else:
        fine = random.randint(100, 500)
        await update_wallet(user_id, -fine)
        await add_xp(user_id, 5)
        text = (
            f"🚔 **BUSTED!**\n"
            f"━━━━━━━━━━━━━━\n"
            f"You got caught trying: {scenario}\n"
            f"💸 Fine: **{fine:,}** coins\n"
            f"━━━━━━━━━━━━━━"
        )

    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("beg") & filters.group)
@error_handler
@rate_limit(3)
async def beg_command(client: Client, message: Message):
    """Beg for coins. Short cooldown."""
    user_id = message.from_user.id
    allowed, remaining = cooldown.check(user_id, "beg", 60)
    if not allowed:
        await message.reply_text(f"⏳ Wait `{remaining}s` before begging again.", quote=True)
        return

    response, min_pay, max_pay = random.choice(_BEG_RESPONSES)
    if max_pay == 0:
        await add_xp(user_id, 2)
        await message.reply_text(f"🙏 {response}... you got nothing.", quote=True)
        return

    earned = random.randint(min_pay, max_pay)
    await update_wallet(user_id, earned)
    await add_xp(user_id, 3)
    await message.reply_text(
        f"🙏 {response}\n💰 You received **{earned:,}** coins!",
        quote=True,
    )


@Client.on_message(filters.command("fish") & filters.group)
@error_handler
@rate_limit(3)
async def fish_command(client: Client, message: Message):
    """Go fishing! 15min cooldown."""
    user_id = message.from_user.id
    allowed, remaining = cooldown.check(user_id, "fish", 900)
    if not allowed:
        mins = remaining // 60
        secs = remaining % 60
        await message.reply_text(f"⏳ Wait `{mins}m {secs}s` to fish again.", quote=True)
        return

    catch, min_pay, max_pay = random.choice(_FISH)
    if max_pay == 0:
        await add_xp(user_id, 2)
        await message.reply_text(f"🎣 You caught: {catch}\n💰 Worth nothing...", quote=True)
        return

    earned = random.randint(min_pay, max_pay)
    await update_wallet(user_id, earned)
    xp_result = await add_xp(user_id, 8)

    text = f"🎣 **FISHING!**\n━━━━━━━━━━━━━━\nYou caught: {catch}\n💰 Sold for **{earned:,}** coins\n━━━━━━━━━━━━━━"
    if xp_result["leveled_up"]:
        text += f"\n\n🎉 **LEVEL UP!** → Level **{xp_result['new_level']}**"
    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("hunt") & filters.group)
@error_handler
@rate_limit(3)
async def hunt_command(client: Client, message: Message):
    """Go hunting! 15min cooldown."""
    user_id = message.from_user.id
    allowed, remaining = cooldown.check(user_id, "hunt", 900)
    if not allowed:
        mins = remaining // 60
        secs = remaining % 60
        await message.reply_text(f"⏳ Wait `{mins}m {secs}s` to hunt again.", quote=True)
        return

    catch, min_pay, max_pay = random.choice(_HUNT)
    if max_pay == 0:
        await add_xp(user_id, 2)
        await message.reply_text(f"🏹 {catch}", quote=True)
        return

    earned = random.randint(min_pay, max_pay)
    await update_wallet(user_id, earned)
    xp_result = await add_xp(user_id, 8)

    text = f"🏹 **HUNTING!**\n━━━━━━━━━━━━━━\nYou caught: {catch}\n💰 Sold for **{earned:,}** coins\n━━━━━━━━━━━━━━"
    if xp_result["leveled_up"]:
        text += f"\n\n🎉 **LEVEL UP!** → Level **{xp_result['new_level']}**"
    await message.reply_text(text, quote=True)

"""
Auralyx Music — Fun & Social
/afk, /marry, /divorce, /trivia, /roll, /8ball
"""

import random
import time
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from database.mongo import (
    set_afk, clear_afk, get_user_economy,
    set_partner, clear_partner, add_xp,
)

logger = logging.getLogger(__name__)

# ── AFK System ──
@Client.on_message(filters.command("afk"))
@error_handler
async def afk_command(client: Client, message: Message):
    """Set AFK status."""
    user_id = message.from_user.id
    reason = " ".join(message.command[1:]) or "AFK"

    await set_afk(user_id, reason)
    await message.reply_text(
        f"💤 **{message.from_user.first_name}** is now AFK.\n• Reason: _{reason}_",
        quote=True,
    )


@Client.on_message(filters.group & ~filters.command(["afk"]) & filters.text, group=99)
async def afk_checker(client: Client, message: Message):
    """Check if user is back from AFK / if mentioned user is AFK."""
    if not message.from_user:
        return

    # Check if sender was AFK
    user_id = message.from_user.id
    doc = await get_user_economy(user_id)
    if doc.get("afk", ""):
        afk_time = doc.get("afk_time", 0)
        ago = int(time.time()) - afk_time
        mins = ago // 60
        await clear_afk(user_id)
        await message.reply_text(
            f"👋 **{message.from_user.first_name}** is back! Was AFK for `{mins}` minutes.",
            quote=True,
        )
        return

    # Check if replied user is AFK
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        doc = await get_user_economy(target_id)
        afk_msg = doc.get("afk", "")
        if afk_msg:
            afk_time = doc.get("afk_time", 0)
            ago = int(time.time()) - afk_time
            mins = ago // 60
            await message.reply_text(
                f"💤 **{message.reply_to_message.from_user.first_name}** is AFK ({mins}m ago)\n• _{afk_msg}_",
                quote=True,
            )


# ── Marriage System ──
@Client.on_message(filters.command("marry") & filters.group)
@error_handler
@rate_limit(10)
async def marry_command(client: Client, message: Message):
    """Propose to someone. Reply, user ID, or @username."""
    from utils.target import resolve_target

    user_id = message.from_user.id
    target_id, target_name, _ = await resolve_target(client, message)

    if not target_id:
        await message.reply_text("• Reply to someone or: `/marry <user_id|@user>` 💍", quote=True)
        return

    if user_id == target_id:
        await message.reply_text("• You can't marry yourself! 😅", quote=True)
        return

    # Check if either is already married
    doc = await get_user_economy(user_id)
    if doc.get("partner_id", 0):
        await message.reply_text("• You're already married! Use `/divorce` first.", quote=True)
        return

    t_doc = await get_user_economy(target_id)
    if t_doc.get("partner_id", 0):
        await message.reply_text("• They're already married!", quote=True)
        return

    await set_partner(user_id, target_id)
    await add_xp(user_id, 50)
    await add_xp(target_id, 50)

    await message.reply_text(
        f"💍 **MARRIED!**\n"
        f"━━━━━━━━━━━━━━\n"
        f"**{message.from_user.first_name}** 💕 **{target_name}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"✨ Both received +50 XP!",
        quote=True,
    )


@Client.on_message(filters.command("divorce") & filters.group)
@error_handler
@rate_limit(10)
async def divorce_command(client: Client, message: Message):
    """Divorce your partner."""
    user_id = message.from_user.id
    doc = await get_user_economy(user_id)
    partner_id = doc.get("partner_id", 0)

    if not partner_id:
        await message.reply_text("• You're not married!", quote=True)
        return

    await clear_partner(user_id)
    await message.reply_text(
        f"💔 **Divorced!**\n"
        f"• You are now single.",
        quote=True,
    )


# ── Fun Commands ──
@Client.on_message(filters.command("roll"))
@error_handler
async def roll_command(client: Client, message: Message):
    """Roll a dice (1-6, or custom range)."""
    max_val = 6
    if len(message.command) >= 2:
        try:
            max_val = int(message.command[1])
            max_val = max(1, min(max_val, 1000000))
        except ValueError:
            pass

    result = random.randint(1, max_val)
    await message.reply_text(f"🎲 Rolled **{result}** (1-{max_val})", quote=True)


@Client.on_message(filters.command("8ball"))
@error_handler
async def eightball_command(client: Client, message: Message):
    """Magic 8-ball."""
    if len(message.command) < 2:
        await message.reply_text("• Ask me a question! `/8ball <question>`", quote=True)
        return

    answers = [
        "🎱 It is certain.",
        "🎱 Without a doubt.",
        "🎱 Yes, definitely.",
        "🎱 You may rely on it.",
        "🎱 Most likely.",
        "🎱 Outlook good.",
        "🎱 Signs point to yes.",
        "🎱 Reply hazy, try again.",
        "🎱 Ask again later.",
        "🎱 Better not tell you now.",
        "🎱 Cannot predict now.",
        "🎱 Concentrate and ask again.",
        "🎱 Don't count on it.",
        "🎱 My reply is no.",
        "🎱 My sources say no.",
        "🎱 Outlook not so good.",
        "🎱 Very doubtful.",
    ]
    await message.reply_text(random.choice(answers), quote=True)


# ── Trivia ──
_TRIVIA_QUESTIONS = [
    ("What planet is known as the Red Planet?", "mars"),
    ("How many continents are there?", "7"),
    ("What is the capital of France?", "paris"),
    ("What is the largest ocean?", "pacific"),
    ("Who painted the Mona Lisa?", "da vinci"),
    ("What is the hardest natural substance?", "diamond"),
    ("How many bones in the human body?", "206"),
    ("What gas do plants absorb?", "carbon dioxide"),
    ("What is the speed of light in km/s (approx)?", "300000"),
    ("What is the smallest prime number?", "2"),
    ("What is the chemical symbol for gold?", "au"),
    ("Who wrote Romeo and Juliet?", "shakespeare"),
    ("What year did World War II end?", "1945"),
    ("What is the largest country by area?", "russia"),
    ("What is H2O commonly known as?", "water"),
]

_active_trivia: dict[int, tuple[str, str]] = {}  # chat_id -> (question, answer)


@Client.on_message(filters.command("trivia") & filters.group)
@error_handler
@rate_limit(10)
async def trivia_command(client: Client, message: Message):
    """Start a trivia question."""
    chat_id = message.chat.id

    if chat_id in _active_trivia:
        q, a = _active_trivia[chat_id]
        await message.reply_text(f"❓ There's already an active question!\n**{q}**", quote=True)
        return

    q, a = random.choice(_TRIVIA_QUESTIONS)
    _active_trivia[chat_id] = (q, a)

    await message.reply_text(
        f"❓ **TRIVIA TIME!**\n"
        f"━━━━━━━━━━━━━━\n"
        f"**{q}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"💡 Type your answer! First correct wins coins!",
        quote=True,
    )


@Client.on_message(filters.group & filters.text & ~filters.command([""]), group=98)
async def trivia_answer_checker(client: Client, message: Message):
    """Check if someone answered the trivia correctly."""
    if not message.from_user or not message.text:
        return

    chat_id = message.chat.id
    if chat_id not in _active_trivia:
        return

    _, correct_answer = _active_trivia[chat_id]
    user_answer = message.text.strip().lower()

    if correct_answer.lower() in user_answer:
        del _active_trivia[chat_id]
        reward = random.randint(100, 500)
        from database.mongo import update_wallet
        await update_wallet(message.from_user.id, reward)
        xp_result = await add_xp(message.from_user.id, 30)

        text = (
            f"🎉 **CORRECT!** {message.from_user.mention}\n"
            f"💰 Reward: **{reward:,}** coins • ✨ +30 XP"
        )
        if xp_result["leveled_up"]:
            text += f"\n🎉 **LEVEL UP!** → Level **{xp_result['new_level']}**"
        await message.reply_text(text, quote=True)

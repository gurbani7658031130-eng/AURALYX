"""
Auralyx Music — Economy: Gambling
/coinflip, /slots, /duel, /blackjack, /roulette
"""

import random
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from utils.cooldown import cooldown
from database.mongo import (
    get_user_economy, atomic_update_wallet, update_wallet,
    update_game_stats, add_xp,
)

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("coinflip") & filters.group)
@error_handler
@rate_limit(3)
async def coinflip_command(client: Client, message: Message):
    """50/50 coin flip gamble."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/coinflip <amount>`", quote=True)
        return

    user_id = message.from_user.id

    try:
        amount = int(message.command[1])
    except ValueError:
        await message.reply_text("• Amount must be a number.", quote=True)
        return

    if amount <= 0:
        await message.reply_text("• Amount must be positive.", quote=True)
        return

    if amount > 50000:
        await message.reply_text("• Maximum bet is 💰 **50,000**.", quote=True)
        return

    # Deduct first (atomic)
    success = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Not enough coins.", quote=True)
        return

    won = random.random() < 0.5
    if won:
        winnings = amount * 2
        await update_wallet(user_id, winnings)
        await update_game_stats(user_id, True)
        await add_xp(user_id, 15)
        await message.reply_text(
            f"🪙 **COINFLIP — HEADS!**\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎉 You **WON** 💰 **{winnings:,}** coins!\n"
            f"━━━━━━━━━━━━━━",
            quote=True,
        )
    else:
        await update_game_stats(user_id, False)
        await add_xp(user_id, 5)
        await message.reply_text(
            f"🪙 **COINFLIP — TAILS!**\n"
            f"━━━━━━━━━━━━━━\n"
            f"💸 You **LOST** 💰 **{amount:,}** coins.\n"
            f"━━━━━━━━━━━━━━",
            quote=True,
        )


# ── Slot Machine Symbols ──
_SLOT_SYMBOLS = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎", "7️⃣"]
_SLOT_MULTIPLIERS = {
    "💎💎💎": 10, "7️⃣7️⃣7️⃣": 7, "⭐⭐⭐": 5,
    "🍉🍉🍉": 4, "🍊🍊🍊": 3, "🍋🍋🍋": 2, "🍒🍒🍒": 2,
}


@Client.on_message(filters.command("slots") & filters.group)
@error_handler
@rate_limit(3)
async def slots_command(client: Client, message: Message):
    """Slot machine gamble."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/slots <amount>`", quote=True)
        return

    user_id = message.from_user.id

    try:
        amount = int(message.command[1])
    except ValueError:
        await message.reply_text("• Amount must be a number.", quote=True)
        return

    if amount <= 0 or amount > 50000:
        await message.reply_text("• Bet between 1 and 50,000.", quote=True)
        return

    success = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Not enough coins.", quote=True)
        return

    # Spin!
    s1 = random.choice(_SLOT_SYMBOLS)
    s2 = random.choice(_SLOT_SYMBOLS)
    s3 = random.choice(_SLOT_SYMBOLS)
    combo = f"{s1}{s2}{s3}"

    multiplier = _SLOT_MULTIPLIERS.get(combo, 0)
    # Two matching = 1.5x
    if multiplier == 0 and (s1 == s2 or s2 == s3 or s1 == s3):
        multiplier = 1.5

    if multiplier > 0:
        winnings = int(amount * multiplier)
        await update_wallet(user_id, winnings)
        await update_game_stats(user_id, True)
        await add_xp(user_id, 20)
        result = f"🎉 **WIN!** 💰 **{winnings:,}** ({multiplier}x)"
    else:
        await update_game_stats(user_id, False)
        await add_xp(user_id, 5)
        result = f"💸 **LOST** 💰 **{amount:,}**"

    await message.reply_text(
        f"🎰 **SLOTS**\n"
        f"━━━━━━━━━━━━━━\n"
        f"  [ {s1} | {s2} | {s3} ]\n"
        f"━━━━━━━━━━━━━━\n"
        f"{result}",
        quote=True,
    )


@Client.on_message(filters.command("duel") & filters.group)
@error_handler
@rate_limit(5)
async def duel_command(client: Client, message: Message):
    """Challenge someone to a coin duel via reply."""
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("• Reply to someone to duel!", quote=True)
        return

    if len(message.command) < 2:
        await message.reply_text("• Usage: Reply with `/duel <amount>`", quote=True)
        return

    user_id = message.from_user.id
    target_id = message.reply_to_message.from_user.id

    if user_id == target_id:
        await message.reply_text("• Can't duel yourself.", quote=True)
        return

    try:
        amount = int(message.command[1])
    except ValueError:
        await message.reply_text("• Amount must be a number.", quote=True)
        return

    if amount <= 0 or amount > 25000:
        await message.reply_text("• Bet between 1 and 25,000.", quote=True)
        return

    # Check both balances
    success1 = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success1:
        await message.reply_text("• You don't have enough coins.", quote=True)
        return

    success2 = await atomic_update_wallet(target_id, -amount, min_balance=0)
    if not success2:
        await update_wallet(user_id, amount)  # Refund challenger
        await message.reply_text("• Your opponent doesn't have enough coins.", quote=True)
        return

    # Fight!
    winner_id = random.choice([user_id, target_id])
    loser_id = target_id if winner_id == user_id else user_id
    winnings = amount * 2
    await update_wallet(winner_id, winnings)
    await update_game_stats(winner_id, True)
    await update_game_stats(loser_id, False)
    await add_xp(winner_id, 25)
    await add_xp(loser_id, 10)

    winner_name = message.from_user.first_name if winner_id == user_id else message.reply_to_message.from_user.first_name

    await message.reply_text(
        f"⚔️ **DUEL RESULT**\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏆 **{winner_name}** wins!\n"
        f"💰 Prize: **{winnings:,}** coins\n"
        f"━━━━━━━━━━━━━━",
        quote=True,
    )


@Client.on_message(filters.command("blackjack") & filters.group)
@error_handler
@rate_limit(5)
async def blackjack_command(client: Client, message: Message):
    """Simple blackjack — try to beat the dealer."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/blackjack <amount>`", quote=True)
        return

    user_id = message.from_user.id
    try:
        amount = int(message.command[1])
    except ValueError:
        await message.reply_text("• Amount must be a number.", quote=True)
        return

    if amount <= 0 or amount > 50000:
        await message.reply_text("• Bet between 1 and 50,000.", quote=True)
        return

    success = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Not enough coins.", quote=True)
        return

    # Simple instant blackjack
    cards = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    suits = ["♠️", "♥️", "♦️", "♣️"]

    def draw():
        return random.choice(cards), random.choice(suits)

    def value(hand):
        total = 0
        aces = 0
        for c, _ in hand:
            if c in ("J", "Q", "K"):
                total += 10
            elif c == "A":
                total += 11
                aces += 1
            else:
                total += int(c)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    # Deal
    player = [draw(), draw()]
    dealer = [draw(), draw()]

    # Player auto-hits if under 16
    while value(player) < 16:
        player.append(draw())

    # Dealer auto-hits if under 17
    while value(dealer) < 17:
        dealer.append(draw())

    p_val = value(player)
    d_val = value(dealer)

    p_cards = " ".join(f"{c}{s}" for c, s in player)
    d_cards = " ".join(f"{c}{s}" for c, s in dealer)

    if p_val > 21:
        result = f"💥 **BUST!** You lost 💰 **{amount:,}**"
        await update_game_stats(user_id, False)
        await add_xp(user_id, 5)
    elif d_val > 21 or p_val > d_val:
        winnings = amount * 2
        await update_wallet(user_id, winnings)
        result = f"🎉 **YOU WIN!** 💰 **{winnings:,}**"
        await update_game_stats(user_id, True)
        await add_xp(user_id, 20)
    elif p_val == d_val:
        await update_wallet(user_id, amount)  # Push — refund
        result = "🤝 **PUSH!** Bet returned."
    else:
        result = f"😞 **Dealer wins!** Lost 💰 **{amount:,}**"
        await update_game_stats(user_id, False)
        await add_xp(user_id, 5)

    await message.reply_text(
        f"🃏 **BLACKJACK**\n"
        f"━━━━━━━━━━━━━━\n"
        f"🧑 You: {p_cards} (`{p_val}`)\n"
        f"🤖 Dealer: {d_cards} (`{d_val}`)\n"
        f"━━━━━━━━━━━━━━\n"
        f"{result}",
        quote=True,
    )


@Client.on_message(filters.command("roulette") & filters.group)
@error_handler
@rate_limit(3)
async def roulette_command(client: Client, message: Message):
    """Roulette — bet on red, black, or a number (0-36)."""
    if len(message.command) < 3:
        await message.reply_text(
            "• Usage: `/roulette <amount> <red|black|even|odd|number>`",
            quote=True,
        )
        return

    user_id = message.from_user.id
    try:
        amount = int(message.command[1])
        bet = message.command[2].lower()
    except (ValueError, IndexError):
        await message.reply_text("• Invalid bet.", quote=True)
        return

    if amount <= 0 or amount > 50000:
        await message.reply_text("• Bet between 1 and 50,000.", quote=True)
        return

    success = await atomic_update_wallet(user_id, -amount, min_balance=0)
    if not success:
        await message.reply_text("• Not enough coins.", quote=True)
        return

    # Spin
    result_num = random.randint(0, 36)
    reds = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    result_color = "green" if result_num == 0 else ("red" if result_num in reds else "black")
    color_emoji = "🟢" if result_color == "green" else ("🔴" if result_color == "red" else "⚫")

    won = False
    multiplier = 0

    if bet in ("red", "black"):
        if bet == result_color:
            won = True
            multiplier = 2
    elif bet in ("even", "odd"):
        if result_num != 0:
            is_even = result_num % 2 == 0
            if (bet == "even" and is_even) or (bet == "odd" and not is_even):
                won = True
                multiplier = 2
    else:
        try:
            bet_num = int(bet)
            if bet_num == result_num:
                won = True
                multiplier = 36
        except ValueError:
            await update_wallet(user_id, amount)  # Refund
            await message.reply_text("• Bet `red`, `black`, `even`, `odd`, or a number (0-36).", quote=True)
            return

    if won:
        winnings = amount * multiplier
        await update_wallet(user_id, winnings)
        await update_game_stats(user_id, True)
        await add_xp(user_id, 20)
        result_text = f"🎉 **WIN!** 💰 **{winnings:,}** ({multiplier}x)"
    else:
        await update_game_stats(user_id, False)
        await add_xp(user_id, 5)
        result_text = f"💸 **LOST** 💰 **{amount:,}**"

    await message.reply_text(
        f"🎡 **ROULETTE**\n"
        f"━━━━━━━━━━━━━━\n"
        f"Ball landed on: {color_emoji} **{result_num}** ({result_color})\n"
        f"Your bet: **{bet}**\n"
        f"━━━━━━━━━━━━━━\n"
        f"{result_text}",
        quote=True,
    )

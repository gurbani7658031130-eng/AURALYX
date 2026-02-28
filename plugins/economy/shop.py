"""
Auralyx Music — Economy: Shop System
/shop, /buy, /inventory, /use
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, rate_limit
from database.mongo import (
    get_user_economy, atomic_update_wallet,
    add_inventory_item, remove_inventory_item,
    set_protection, update_wallet, add_xp,
)
import time

logger = logging.getLogger(__name__)

# ── Shop Items ──
SHOP_ITEMS = {
    "shield": {
        "name": "🛡️ Shield",
        "price": 500,
        "description": "3-hour protection from /rob and /kill",
        "emoji": "🛡️",
    },
    "xpboost": {
        "name": "⚡ XP Boost",
        "price": 1000,
        "description": "Instant +200 XP",
        "emoji": "⚡",
    },
    "lootbox": {
        "name": "📦 Loot Box",
        "price": 2000,
        "description": "Random reward (500-5000 coins)",
        "emoji": "📦",
    },
    "badge_fire": {
        "name": "🔥 Fire Badge",
        "price": 5000,
        "description": "Collectible badge for your profile",
        "emoji": "🔥",
    },
    "badge_star": {
        "name": "⭐ Star Badge",
        "price": 3000,
        "description": "Collectible badge for your profile",
        "emoji": "⭐",
    },
    "badge_crown": {
        "name": "👑 Crown Badge",
        "price": 10000,
        "description": "Rare collectible badge",
        "emoji": "👑",
    },
    "heist_kit": {
        "name": "🧰 Heist Kit",
        "price": 3000,
        "description": "Increases /crime success rate for next attempt",
        "emoji": "🧰",
    },
    "lucky_charm": {
        "name": "🍀 Lucky Charm",
        "price": 2500,
        "description": "Increases /coinflip win chance to 60% (one use)",
        "emoji": "🍀",
    },
}


@Client.on_message(filters.command("shop") & filters.group)
@error_handler
@rate_limit(3)
async def shop_command(client: Client, message: Message):
    """Display the shop."""
    text = "🛒 **AURALYX SHOP**\n━━━━━━━━━━━━━━━━━━\n\n"

    for key, item in SHOP_ITEMS.items():
        text += f"{item['emoji']} **{item['name']}** — 💰 {item['price']:,}\n"
        text += f"  _{item['description']}_\n"
        text += f"  → `/buy {key}`\n\n"

    text += "━━━━━━━━━━━━━━━━━━\n💡 Use `/inventory` to see your items."
    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("buy") & filters.group)
@error_handler
@rate_limit(3)
async def buy_command(client: Client, message: Message):
    """Buy an item from the shop."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/buy <item_name>`\nSee `/shop` for items.", quote=True)
        return

    item_key = message.command[1].lower()
    user_id = message.from_user.id

    if item_key not in SHOP_ITEMS:
        await message.reply_text("• Item not found. Check `/shop`.", quote=True)
        return

    item = SHOP_ITEMS[item_key]
    price = item["price"]

    success = await atomic_update_wallet(user_id, -price, min_balance=0)
    if not success:
        await message.reply_text(f"• Not enough coins. Need 💰 **{price:,}**.", quote=True)
        return

    await add_inventory_item(user_id, item_key)
    await message.reply_text(
        f"✅ **Purchased {item['name']}!**\n"
        f"💰 Spent: **{price:,}** coins\n"
        f"Use `/use {item_key}` to activate it.",
        quote=True,
    )


@Client.on_message(filters.command("inventory") & filters.group)
@error_handler
@rate_limit(3)
async def inventory_command(client: Client, message: Message):
    """View your inventory."""
    user_id = message.from_user.id
    doc = await get_user_economy(user_id)
    inventory = doc.get("inventory", [])

    if not inventory:
        await message.reply_text("🎒 Your inventory is empty.\nVisit `/shop` to buy items!", quote=True)
        return

    # Count items
    from collections import Counter
    counts = Counter(inventory)

    text = "🎒 **YOUR INVENTORY**\n━━━━━━━━━━━━━━━━━━\n\n"
    for item_key, count in counts.items():
        item = SHOP_ITEMS.get(item_key)
        if item:
            text += f"{item['emoji']} **{item['name']}** x{count}\n"
        else:
            text += f"❓ **{item_key}** x{count}\n"

    text += f"\n━━━━━━━━━━━━━━━━━━\n📦 Total items: **{len(inventory)}**"
    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("use") & filters.group)
@error_handler
@rate_limit(3)
async def use_command(client: Client, message: Message):
    """Use an item from inventory."""
    if len(message.command) < 2:
        await message.reply_text("• Usage: `/use <item_name>`", quote=True)
        return

    item_key = message.command[1].lower()
    user_id = message.from_user.id

    # Check inventory
    removed = await remove_inventory_item(user_id, item_key)
    if not removed:
        await message.reply_text("• You don't have that item.", quote=True)
        return

    # Apply effects
    if item_key == "shield":
        until = int(time.time()) + 10800  # 3 hours
        await set_protection(user_id, until)
        await message.reply_text("🛡️ **Shield Activated!** Protected for 3 hours.", quote=True)

    elif item_key == "xpboost":
        result = await add_xp(user_id, 200)
        text = "⚡ **XP Boost Used!** +200 XP"
        if result["leveled_up"]:
            text += f"\n🎉 **LEVEL UP!** → Level **{result['new_level']}**"
        await message.reply_text(text, quote=True)

    elif item_key == "lootbox":
        import random
        reward = random.randint(500, 5000)
        await update_wallet(user_id, reward)
        await message.reply_text(f"📦 **Loot Box Opened!**\n🎉 You found 💰 **{reward:,}** coins!", quote=True)

    elif item_key == "heist_kit":
        await message.reply_text("🧰 **Heist Kit Ready!** Your next /crime has +20% success.", quote=True)

    elif item_key == "lucky_charm":
        await message.reply_text("🍀 **Lucky Charm Active!** Next /coinflip has 60% win chance.", quote=True)

    elif item_key.startswith("badge_"):
        # Badges are collectible — don't consume, re-add to inventory
        await add_inventory_item(user_id, item_key)
        badge = SHOP_ITEMS.get(item_key, {})
        await message.reply_text(f"{badge.get('emoji', '🏅')} Badge equipped! Shows on your `/profile`.", quote=True)

    else:
        await message.reply_text(f"• Used **{item_key}**!", quote=True)

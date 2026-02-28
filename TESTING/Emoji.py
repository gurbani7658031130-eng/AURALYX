
# EmojiTester.py
# Sends Telegram Custom Emojis (by ID) from Emoji_id.txt to Saved Messages
# Uses a USER ACCOUNT login (not a bot) — required to send to "Saved Messages"
# Compatible with Python 3.10+ and Pyrogram v2+
#
# FIRST RUN: Pyrogram will ask for your phone number + OTP code.
#            After that, a session file is saved and login is automatic.
#
# Run: python EmojiTester.py

import asyncio
import argparse
import sys
import random
import os

from pyrogram import Client
from pyrogram.enums import MessageEntityType
from pyrogram.types import MessageEntity
from pyrogram.errors import FloodWait, RPCError

# ──────────────────────────────────────────────
# CONFIGURATION
# Get API_ID and API_HASH from: https://my.telegram.org
# Do NOT put a BOT_TOKEN here — this must be a user account login.
# ──────────────────────────────────────────────
# CONFIGURATION — Replace with your credentials
# ──────────────────────────────────────────────
API_ID    = 28807899                   # Your API ID   → my.telegram.org
API_HASH  = "f5a090037ba4cc92c3a87e4744e66003"      # Your API Hash → my.telegram.org
BOT_TOKEN = "8717096677:AAGUqsdseZfmHrDKkP11AeNT_TU_GIaZQc0"     # Your Bot Token → @BotFather

SESSION_NAME  = "emoji_tester_session"   # Session file (auto-created)
EMOJI_ID_FILE = "Emoji_id.txt"           # Must be in the same folder as this script


# Placeholder visible character — Telegram requires at least 1 char in the message.
# This single character is what the custom emoji "wraps" over visually.
PLACEHOLDER     = "⭐"
PLACEHOLDER_LEN = 1   # UTF-16 length of ⭐ (single code unit)

def load_emoji_ids(filepath: str) -> list[int]:
    if not os.path.exists(filepath):
        print(f"[✗] File not found: {filepath}")
        print("     → Make sure Emoji_id.txt is in the same folder as this script.")
        sys.exit(1)

    ids = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                ids.append(int(line))
            except ValueError:
                print(f"  [!] Skipping invalid line: {line!r}")

    return ids


# ──────────────────────────────────────────────
# ARGUMENT PARSER
# ──────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Telegram Custom Emoji Tester — sends emoji IDs to Saved Messages"
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Seconds between messages (default: random 0.3–0.5s)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of emojis to send (default: all)"
    )

    parser.add_argument(
        "--chat-id",
        type=str,
        default=None,
        help="Target chat ID or @username (default: your Saved Messages)"
    )

    parser.add_argument(
        "--file",
        type=str,
        default=EMOJI_ID_FILE,
        help=f"Path to emoji ID file (default: {EMOJI_ID_FILE})"
    )

    return parser.parse_args()


# ──────────────────────────────────────────────
# SEND A SINGLE CUSTOM EMOJI
# MessageEntityType.CUSTOM_EMOJI is required in Pyrogram v2 (not a plain string)
# ──────────────────────────────────────────────
async def send_custom_emoji(app: Client, chat_id, emoji_id: int):
    entity = MessageEntity(
        type=MessageEntityType.CUSTOM_EMOJI,
        offset=0,
        length=PLACEHOLDER_LEN,
        custom_emoji_id=emoji_id,
    )

    await app.send_message(
        chat_id=chat_id,
        text=PLACEHOLDER,
        entities=[entity],
    )


# ──────────────────────────────────────────────
# MAIN ASYNC FUNCTION
# ──────────────────────────────────────────────
async def main():
    args = parse_args()

    # Load and optionally slice IDs
    all_ids   = load_emoji_ids(args.file)
    emoji_ids = all_ids[: args.limit] if args.limit else all_ids
    total     = len(emoji_ids)

    # Default target is "me" = Saved Messages (only works with user accounts)
    target = args.chat_id if args.chat_id else "me"

    print("=" * 55)
    print("   Telegram Custom Emoji Tester  —  Pyrogram v2+")
    print("=" * 55)
    print(f"   File       : {args.file}")
    print(f"   Total IDs  : {len(all_ids)}  |  Sending: {total}")
    print(f"   Target     : {target}")
    print(f"   Delay      : {'random 0.3–0.5s' if args.delay is None else f'{args.delay}s'}")
    print("=" * 55)
    print()
    print("  NOTE: On first run, Pyrogram will ask for your")
    print("        phone number and the OTP sent by Telegram.")
    print("        This is normal — it logs you in as a user.")
    print()

    # User account client — no bot_token parameter
    app = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        # No bot_token here! This is a user account login.
    )

    sent   = 0
    failed = 0

    try:
        async with app:
            print("[✓] Connected to Telegram.\n")

            for index, emoji_id in enumerate(emoji_ids, start=1):

                try:
                    await send_custom_emoji(app, target, emoji_id)
                    sent += 1
                    print(f"  Sending #{index:>3}/{total}  →  ID: {emoji_id}  ✓")

                except FloodWait as e:
                    print(f"\n  [!] FloodWait — sleeping {e.value}s...\n")
                    await asyncio.sleep(e.value)

                    # Retry once after flood wait
                    try:
                        await send_custom_emoji(app, target, emoji_id)
                        sent += 1
                        print(f"  Retry  #{index:>3}/{total}  →  ID: {emoji_id}  ✓")
                    except Exception as retry_err:
                        failed += 1
                        print(f"  [✗] Retry failed  →  ID: {emoji_id}  |  {retry_err}")

                except RPCError as e:
                    failed += 1
                    print(f"  [✗] RPC error  →  ID: {emoji_id}  |  {e}")

                except Exception as e:
                    failed += 1
                    print(f"  [✗] Error      →  ID: {emoji_id}  |  {e}")

                # Delay between sends to stay under flood limits
                delay = args.delay if args.delay is not None else random.uniform(0.3, 0.5)
                await asyncio.sleep(delay)

    except Exception as e:
        print(f"\n[✗] Login/connection error: {e}")
        print("     → Make sure API_ID and API_HASH are correct.")
        print("     → Delete the .session file and try again if login is stuck.")
        sys.exit(1)

    # ── Final Summary ──
    print()
    print("=" * 55)
    print("   FINAL SUMMARY")
    print("=" * 55)
    print(f"   Total emojis  : {total}")
    print(f"   Sent          : {sent}")
    print(f"   Failed        : {failed}")
    print(f"   Target chat   : {target}")
    print("=" * 55)
    print("   Done! Open Telegram to see your custom emojis.\n")


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
    
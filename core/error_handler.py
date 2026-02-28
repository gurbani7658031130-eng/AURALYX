"""
Auralyx Music — Global Error Handler
Catches all unhandled exceptions, logs to LOG_CHANNEL, prevents crash.
"""

import logging
import traceback
from datetime import datetime
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery
from config import LOG_CHANNEL_ID, SUDO_USERS

logger = logging.getLogger(__name__)
_sending_error = False

import os
import re

def sanitize_text(text: str) -> str:
    """
    Remove sensitive information from text:
    - Absolute file paths (Windows/Unix)
    - Potential tokens/keys
    """
    if not text:
        return ""
    
    # 1. Mask Absolute Paths (Windows & Unix)
    # Windows: C:\Users\anmol\Desktop\AuralyxMusic\core\vip.py -> \core\vip.py
    # This regex looks for Windows drive letters and long paths
    cwd = os.getcwd()
    if cwd:
        text = text.replace(cwd, "[ROOT]")
        
    # Mask User paths (Windows)
    text = re.sub(r'[a-zA-Z]:\\Users\\[^\\]+\\', r'~\\', text)
    
    # 2. Mask Sensitive Tokens (Generic regex for bot tokens, mongo uris)
    # Bot Token: 1234567890:ABC-DEF_GHI
    text = re.sub(r'\d{8,12}:[a-zA-Z0-9_-]{35,}', '[TOKEN_MASKED]', text)
    # Mongo URI: mongodb+srv://user:pass@host
    text = re.sub(r'mongodb\+srv://[^:]+:[^@]+@', 'mongodb+srv://[CREDENTIALS_MASKED]@', text)

    return text


async def report_error(client: Client, handler_name: str, error: Exception,
                       user_id: int = 0, chat_id: int = 0):
    """Send a formatted error report to the log channel."""
    global _sending_error
    if _sending_error or not LOG_CHANNEL_ID:
        return
    _sending_error = True

    try:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_text = "".join(tb)
        
        # Sanitization
        tb_text = sanitize_text(tb_text)
        error_msg = sanitize_text(str(error))

        # Truncate to avoid Telegram 4096 char limit
        if len(tb_text) > 2500:
            tb_text = tb_text[:1200] + "\n\n... truncated ...\n\n" + tb_text[-1200:]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = (
            f"⚠️ <b>ERROR REPORT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Handler:</b> <code>{handler_name}</code>\n"
            f"<b>User:</b> <code>{user_id}</code>\n"
            f"<b>Chat:</b> <code>{chat_id}</code>\n"
            f"<b>Time:</b> <code>{timestamp}</code>\n"
            f"<b>Error:</b> <code>{type(error).__name__}: {error_msg[:200]}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<pre>{tb_text}</pre>"
        )

        # Truncate entire message if still too long
        if len(report) > 4000:
            report = report[:4000] + "</pre>"

        from pyrogram import enums
        await client.send_message(
            LOG_CHANNEL_ID,
            report,
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as e:
        logger.error("Failed to send error report to log channel: %s", e)
    finally:
        _sending_error = False

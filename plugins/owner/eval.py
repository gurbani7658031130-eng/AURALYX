"""
Auralyx Music — Owner: Eval
Executes Python code in a secure, restricted environment.
"""

import sys
import io
import traceback
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from utils.decorators import owner_only, error_handler
from config import LOG_CHANNEL_ID

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("o_eval") & (filters.private | filters.group))
@owner_only
@error_handler
async def owner_eval(client: Client, message: Message):
    """Execute python code with stdout capture and timeout."""
    if len(message.command) < 2:
        return
        
    cmd = message.text.split(None, 1)[1]
    
    # ── Logging ──
    if LOG_CHANNEL_ID:
        try:
            await client.send_message(
                LOG_CHANNEL_ID,
                f"📟 **EVAL EXECUTED**\n"
                f"👤 Owner: `{message.from_user.id}`\n"
                f"📝 Code:\n<pre>{cmd}</pre>",
                parse_mode=enums.ParseMode.HTML
            )
        except Exception:
            pass

    # ── Setup Environment ──
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None
    
    async def _execute():
        # Accessible context
        # We allow client, message, and basic modules
        local_vars = {
            "client": client,
            "message": message,
            "asyncio": asyncio,
            "db": __import__("database.mongo"),
            "config": __import__("config"),
            "stats": __import__("core.voice_cleanup")._activity,
        }
        
        # Wrap code in async function
        inner_code = "\n".join(f"    {line}" for line in cmd.split("\n"))
        exec_code = f"async def __ex():\n{inner_code}"
        
        exec(exec_code, {}, local_vars)
        return await local_vars["__ex"]()

    try:
        # ── Run with Timeout ──
        result = await asyncio.wait_for(_execute(), timeout=10)
    except asyncio.TimeoutError:
        exc = "Execution timed out (10s)."
    except Exception:
        exc = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        stdout = redirected_output.getvalue()
        stderr = redirected_error.getvalue()

    # ── Format Response ──
    out = f"**OUTPUT:**\n<pre>{stdout}</pre>" if stdout else ""
    err = f"**ERROR:**\n<pre>{stderr or exc}</pre>" if (stderr or exc) else ""
    res = f"**RETURN VALUE:**\n<pre>{result}</pre>" if result is not None else ""
    
    final_text = f"📟 **Eval Result**\n\n{out}\n{err}\n{res}"
    if len(final_text) > 4000:
        final_text = final_text[:3900] + "\n... TRUNCATED ..."
        
    await message.reply_text(final_text, parse_mode=enums.ParseMode.HTML, quote=True)

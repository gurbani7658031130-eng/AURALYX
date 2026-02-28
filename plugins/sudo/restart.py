"""
Auralyx Music — Sudo: Restart
Gracefully stops everything and restarts the process.
"""

import os
import sys
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from utils.decorators import error_handler, permission_required
from utils.emojis import Emojis

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("restart") & (filters.private | filters.group))
@permission_required("restart")
@error_handler
async def restart_command(client: Client, message: Message):
    """Gracefully restart the bot."""
    msg = await message.reply_text("🔄 **Restarting Auralyx Music...**\n_Please wait a moment._")
    
    # ── Shutdown Logic ──
    from core.call import call_manager
    from core.assistant import assistant
    from core.voice_cleanup import stop_cleanup
    from utils.stream import cleanup_all
    
    logger.info("Sudo restart requested by %s", message.from_user.id)
    
    # Stop background tasks
    stop_cleanup()
    
    # Disconnect all active VCs
    for cid in list(call_manager._calls):
        try:
            gc = call_manager._calls[cid]
            gc.stop_playout()
            await gc.leave_current_group_call()
        except Exception:
            pass
    
    await cleanup_all()
        
    # Stop clients
    await assistant.stop()
    await client.stop()
    
    # Give OS a chance to clean up sockets
    await asyncio.sleep(2)
    
    # ── Restart via exec ──
    os.execv(sys.executable, [sys.executable, "main.py"])

"""
Auralyx Music — Voice Chat Auto-Cleanup
Background task that leaves dead voice chats after inactivity.
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Per-chat last activity timestamps
_activity: dict[int, float] = {}

# Background task reference
_cleanup_task: Optional[asyncio.Task] = None

INACTIVITY_TIMEOUT = 600  # 10 minutes
CHECK_INTERVAL = 300       # 5 minutes


def record_activity(chat_id: int):
    """Record that music activity happened in a chat. Call on /play, /skip, etc."""
    _activity[chat_id] = time.time()


def remove_chat(chat_id: int):
    """Remove a chat from tracking (called on /stop or leave)."""
    _activity.pop(chat_id, None)


async def _cleanup_loop(bot_client):
    """Background loop: check for inactive VCs every CHECK_INTERVAL seconds."""
    from core.call import call_manager
    from utils.queue import clear_queue, get_queue
    from utils.stream import kill_stream
    import random
    
    while True:
        try:
            # Jitter: Spread out the cleanup interval across multiple shards/bots
            jitter = random.uniform(-10.0, 10.0)
            await asyncio.sleep(CHECK_INTERVAL + jitter)
            
            now = time.time()
            stale_chats = [
                chat_id for chat_id, last in _activity.items()
                if now - last > INACTIVITY_TIMEOUT
            ]

            for chat_id in stale_chats:
                try:
                    # Don't leave if there are still tracks in the queue
                    if get_queue(chat_id):
                        record_activity(chat_id)  # Refresh — music is still active
                        continue

                    logger.info("Auto-cleaning inactive VC in chat %s", chat_id)
                    gc = call_manager.get(chat_id)
                    try:
                        gc.stop_playout()
                        await gc.leave_current_group_call()
                    except Exception:
                        pass
                    await kill_stream(chat_id)
                    clear_queue(chat_id)
                    remove_chat(chat_id)
                    call_manager.remove(chat_id)
                except Exception as e:
                    logger.error("Cleanup error for chat %s: %s", chat_id, e)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Voice cleanup loop error (Auto-recovering in 10s): %s", e)
            await asyncio.sleep(10)


def start_cleanup(bot_client):
    """Start the background cleanup task. Call once at startup."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        return  # Already running, prevent duplicates
    _cleanup_task = asyncio.create_task(_cleanup_loop(bot_client))
    logger.info("Voice chat auto-cleanup started (check every %ss, timeout %ss)",
                CHECK_INTERVAL, INACTIVITY_TIMEOUT)


def stop_cleanup():
    """Stop the background cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
    _cleanup_task = None

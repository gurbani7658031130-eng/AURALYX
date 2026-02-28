"""
Auralyx Music - Entry Point
Starts the bot, assistant, loads all plugin modules, and keeps alive.
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Load env first.
load_dotenv()

# Ensure stdout can safely render logs on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Pyrogram 2.0.106 has a hardcoded MIN_CHANNEL_ID that can be too small
# for newer Telegram channel IDs.
import pyrogram.utils

pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

# PyTgCalls 3.0.0.dev can timeout too aggressively during FloodWait handling.
try:
    from pytgcalls.implementation.group_call_base import GroupCallBase

    setattr(GroupCallBase, "_GroupCallBase__ASYNCIO_TIMEOUT", 30.0)
except Exception:
    pass

from config import LOG_LEVEL, validate_config
from core.bot import AuralyxBot
from core.maintenance import load_state as load_maintenance
from core.sudo_acl import invalidate_cache as invalidate_sudo_cache
from core.shadowban import load_state as load_shadowbans
from core.voice_cleanup import start_cleanup, stop_cleanup
from database.approval_sqlite import init_db as init_approval_db
from database.mongo import ensure_indexes
from utils.stream import cleanup_all as cleanup_streams

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("AuralyxMusic")
_periodic_task = None
_instance_lock_path = os.path.join(os.path.dirname(__file__), ".cache", "bot.pid")


def _acquire_instance_lock() -> bool:
    """Prevent running multiple bot instances simultaneously."""
    os.makedirs(os.path.dirname(_instance_lock_path), exist_ok=True)
    current_pid = os.getpid()

    if os.path.exists(_instance_lock_path):
        try:
            with open(_instance_lock_path, "r", encoding="utf-8") as f:
                old_pid = int((f.read() or "0").strip())
        except Exception:
            old_pid = 0

        if old_pid and old_pid != current_pid:
            try:
                import psutil

                if psutil.pid_exists(old_pid):
                    logger.critical(
                        "Another bot instance is already running (PID %s). Stop it first.",
                        old_pid,
                    )
                    return False
            except Exception:
                # If we cannot verify process state, fail safe by replacing stale lock.
                pass

    try:
        with open(_instance_lock_path, "w", encoding="utf-8") as f:
            f.write(str(current_pid))
        return True
    except Exception as e:
        logger.critical("Failed to create instance lock: %s", e)
        return False


def _release_instance_lock():
    try:
        if os.path.exists(_instance_lock_path):
            with open(_instance_lock_path, "r", encoding="utf-8") as f:
                lock_pid = int((f.read() or "0").strip())
            if lock_pid == os.getpid():
                os.remove(_instance_lock_path)
    except Exception:
        pass


async def _periodic_cleanup():
    """
    Background task that periodically cleans stale entries from in-memory
    data structures to prevent unbounded growth.
    """
    from utils.cooldown import cooldown
    from utils.decorators import cleanup_rate_limits

    while True:
        try:
            await asyncio.sleep(600)

            cd_removed = cooldown.cleanup(max_age=3600)
            rl_removed = cleanup_rate_limits(max_age=300)

            if cd_removed or rl_removed:
                logger.debug(
                    "Periodic cleanup: removed %d cooldowns, %d rate limits",
                    cd_removed,
                    rl_removed,
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Periodic cleanup error: %s", e)
            await asyncio.sleep(30)


async def main():
    """Initialize and run the Auralyx Music bot."""
    global _periodic_task

    logger.info("================================")
    logger.info("  Auralyx Music - Starting Up")
    logger.info("================================")

    if not _acquire_instance_lock():
        sys.exit(1)

    validate_config()

    # Database and core state
    try:
        await ensure_indexes()
        await init_approval_db()
        await invalidate_sudo_cache()
        await load_maintenance()
        await load_shadowbans()
        logger.info("Core systems initialized.")
    except Exception as e:
        logger.warning("System init error (non-fatal): %s", e)

    bot = AuralyxBot()

    from core.call import assistant, call_manager

    logger.info("Starting assistant...")
    await assistant.start()

    logger.info("Starting bot client...")
    await bot.start()

    from config import LOG_CHANNEL_ID

    if LOG_CHANNEL_ID:
        try:
            await bot.resolve_peer(LOG_CHANNEL_ID)
            logger.info("Log channel peer resolved successfully.")
        except Exception as e:
            logger.warning(
                "Proactive peer resolution failed (expected if bot has no access yet): %s",
                e,
            )

    start_cleanup(bot)
    _periodic_task = asyncio.create_task(_periodic_cleanup())

    logger.info("================================")
    logger.info("  Auralyx Music - Online")
    logger.info("================================")

    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Shutting down gracefully...")

        if _periodic_task and not _periodic_task.done():
            _periodic_task.cancel()

        stop_cleanup()

        for cid in list(call_manager._calls):
            try:
                gc = call_manager._calls[cid]
                gc.stop_playout()
                await gc.leave_current_group_call()
            except Exception:
                pass
            call_manager.remove(cid)

        await cleanup_streams()

        try:
            await assistant.stop()
        except Exception:
            pass
        try:
            await bot.stop()
        except Exception:
            pass

        logger.info("Auralyx Music shut down cleanly.")
        _release_instance_lock()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Auralyx Music shut down by user.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
    finally:
        _release_instance_lock()
        sys.exit(0)

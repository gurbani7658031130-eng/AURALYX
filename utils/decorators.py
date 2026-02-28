"""
Auralyx Music - Decorators
Ultra-lightweight error handler, rate limiter, and sudo-only wrappers.
"""

import functools
import logging
import time

from pyrogram.types import Message

from config import OWNER_ID
from core.error_handler import report_error
from core.sudo_acl import AVAILABLE_PERMISSIONS, has_permission, is_sudo

logger = logging.getLogger(__name__)

# Extremely lightweight memory cache for rate limits.
_rate_limits: dict[tuple[int, str], float] = {}
_MAX_RATE_ENTRIES = 50000


def cleanup_rate_limits(max_age: int = 300) -> int:
    """Remove stale rate limit entries older than max_age seconds."""
    global _rate_limits
    now = time.monotonic()
    before = len(_rate_limits)
    _rate_limits = {k: v for k, v in _rate_limits.items() if now - v < max_age}
    return before - len(_rate_limits)


def _ensure_bounded():
    """Evict entries if dictionary grows unexpectedly huge."""
    if len(_rate_limits) > _MAX_RATE_ENTRIES:
        cleanup_rate_limits(max_age=60)
        if len(_rate_limits) > _MAX_RATE_ENTRIES:
            _rate_limits.clear()


def error_handler(func):
    """Unified command wrapper with global error reporting."""

    @functools.wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else 0

        try:
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            chat_id = message.chat.id if message.chat else 0
            logger.error("Crash in %s: %s", func.__name__, repr(e))
            await report_error(client, func.__name__, e, user_id, chat_id)
            try:
                await message.reply_text("An error occurred. It has been logged.", quote=True)
            except Exception:
                pass

    return wrapper


def rate_limit(seconds: int = 5):
    """Memory-safe per-user anti-spam cooldown."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(client, message: Message, *args, **kwargs):
            user_id = message.from_user.id if message.from_user else 0
            if user_id == OWNER_ID or await is_sudo(user_id):
                return await func(client, message, *args, **kwargs)

            _ensure_bounded()
            key = (user_id, func.__name__)
            now = time.monotonic()
            last = _rate_limits.get(key, 0)

            if now - last < seconds:
                remaining = int(seconds - (now - last))
                await message.reply_text(
                    f"Slow down. Try again in `{remaining}s`.",
                    quote=True,
                )
                return

            _rate_limits[key] = now
            return await func(client, message, *args, **kwargs)

        return wrapper

    return decorator


def owner_only(func):
    """Decorator restricting command to OWNER_ID only."""

    @functools.wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        if not message.from_user:
            return

        user_id = message.from_user.id
        if user_id != OWNER_ID:
            return

        if hasattr(message, "edit_date") and message.edit_date:
            return

        return await func(client, message, *args, **kwargs)

    return wrapper


def owner_rate_limit(seconds: int = 2):
    """Safety rate limit for owner commands."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(client, message: Message, *args, **kwargs):
            user_id = message.from_user.id if message.from_user else 0
            key = (user_id, f"owner_{func.__name__}")
            now = time.monotonic()
            last = _rate_limits.get(key, 0)

            if now - last < seconds:
                return

            _rate_limits[key] = now
            return await func(client, message, *args, **kwargs)

        return wrapper

    return decorator


def sudo_only(func):
    """Decorator restricting command to dynamic SUDO ACL."""

    @functools.wraps(func)
    async def wrapper(client, message: Message, *args, **kwargs):
        if not message.from_user:
            return

        user_id = message.from_user.id
        if not await is_sudo(user_id):
            await message.reply_text("You are not authorized to use this command.", quote=True)
            return

        if hasattr(message, "edit_date") and message.edit_date:
            return

        return await func(client, message, *args, **kwargs)

    return wrapper


def permission_required(permission_key: str):
    """Decorator restricting command execution by permission key."""
    if permission_key not in AVAILABLE_PERMISSIONS:
        raise ValueError(f"Invalid permission key: {permission_key}")

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(client, message: Message, *args, **kwargs):
            if not message.from_user:
                return

            user_id = message.from_user.id
            if not await has_permission(user_id, permission_key):
                await message.reply_text("You don't have permission to use this command.", quote=True)
                return
            return await func(client, message, *args, **kwargs)

        return wrapper

    return decorator

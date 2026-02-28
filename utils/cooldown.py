"""
Auralyx Music — Central Cooldown Manager
Per-user per-command cooldown tracking with SUDO bypass.
Uses time.monotonic() for robustness and includes periodic cleanup.
"""

import time
from config import SUDO_USERS, OWNER_ID


class CooldownManager:
    """Tracks cooldowns per (user_id, command) pair with bounded memory."""

    def __init__(self, max_entries: int = 50000):
        self._cooldowns: dict[tuple[int, str], float] = {}
        self._max_entries = max_entries

    def check(self, user_id: int, command: str, seconds: int) -> tuple[bool, int]:
        """
        Check if a user can use a command.

        Returns:
            (True, 0) if allowed.
            (False, remaining_seconds) if on cooldown.
        """
        # Owner has autonomous privilege — zero cooldowns
        if user_id == OWNER_ID:
            return True, 0
        if user_id in SUDO_USERS:
            return True, 0

        key = (user_id, command)
        now = time.monotonic()
        last = self._cooldowns.get(key, 0)
        elapsed = now - last

        if elapsed < seconds:
            remaining = int(seconds - elapsed)
            return False, remaining

        # Bounded check before adding
        if len(self._cooldowns) >= self._max_entries:
            self.cleanup()

        self._cooldowns[key] = now
        return True, 0

    def reset(self, user_id: int, command: str) -> None:
        """Reset a specific cooldown."""
        self._cooldowns.pop((user_id, command), None)

    def cleanup(self, max_age: int = 3600) -> int:
        """
        Remove stale cooldown entries older than max_age seconds.
        Returns the number of entries removed.
        """
        now = time.monotonic()
        before = len(self._cooldowns)
        self._cooldowns = {
            k: v for k, v in self._cooldowns.items()
            if now - v < max_age
        }
        removed = before - len(self._cooldowns)
        return removed


# Global singleton
cooldown = CooldownManager()

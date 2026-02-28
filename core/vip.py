"""
Auralyx Music - VIP & Identity System
Handles VIP tiers, badges, and user identity rendering.
"""

import time
from typing import Optional

from core.sudo_acl import is_sudo
from database.mongo import get_user_economy


class VIPManager:
    """Manages VIP levels and badges."""

    LEVELS = {
        0: None,
        1: "[Silver]",
        2: "[Gold]",
        3: "[Platinum]",
    }

    @classmethod
    async def get_user_vip(cls, user_id: int) -> Optional[str]:
        """Get the text VIP badge if active."""
        doc = await get_user_economy(user_id)
        level = doc.get("vip_level", 0)
        expiry = doc.get("vip_expiry", 0)
        if level > 0 and (expiry == 0 or expiry > int(time.time())):
            return cls.LEVELS.get(level)
        return None


class Identity:
    """Composes user display names with badges."""

    @staticmethod
    async def get_name(user_id: int, original_name: str, rank: int = 0) -> str:
        doc = await get_user_economy(user_id)

        sudo_badge = "[SUDO] " if await is_sudo(user_id) else ""

        vip_tier = doc.get("vip_level", 0)
        vip_expiry = doc.get("vip_expiry", 0)

        vip_badge = ""
        if vip_tier > 0 and (vip_expiry == 0 or vip_expiry > int(time.time())):
            tiers = {1: "[Silver]", 2: "[Gold]", 3: "[Platinum]"}
            vip_badge = f"{tiers.get(vip_tier, '[VIP]')} "

        rank_badge = "[TOP1] " if rank == 1 else ""

        title = doc.get("custom_title", "")
        title_str = f"| {title} " if title else ""

        return f"{sudo_badge}{vip_badge}{rank_badge}{original_name} {title_str}".strip()


vip_manager = VIPManager()
identity = Identity()

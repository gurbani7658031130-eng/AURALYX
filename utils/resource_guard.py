"""
Auralyx Music - Resource Stats
Load-protection throttles are disabled by user request.
"""

import psutil


def is_overloaded() -> bool:
    """Load shedding disabled."""
    return False


async def auto_throttle():
    """Auto-throttle disabled."""
    return


def get_resource_stats() -> dict:
    """Return current CPU and RAM usage (direct read)."""
    mem = psutil.virtual_memory()
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram_percent": mem.percent,
        "ram_used_mb": mem.used // (1024 ** 2),
        "ram_total_mb": mem.total // (1024 ** 2),
    }

"""
Auralyx Music — Video Emoji Registry
Centralized storage for custom video emoji IDs.
"""

# ── HOW TO GET REAL VIDEO EMOJI IDS ────────────
# 1. Use /getid command while replying to an animated emoji.
# 2. Copy the numeric ID and paste it below.
# ──────────────────────────────────────────────

# Registry for animated custom emoji IDs (Telegram custom_emoji entities)
VIDEO_EMOJIS = {
    "headphone": "6235332768989976110",
    "music": "6118296387642724858",
    "coin": "6093666528316625608",
    "sword": "6095627640448750533",
    "admin": "6093379246544130083",
    "crown": "5337064406553467864",
    "vip1": "6136444905095961890",
    "vip2": "5377804387559154477",
    "vip3": "5438263516903523162",
    "leader_crown": "5359633141138990064",
    "glow_title": "5267205427749199322",
    "bullet": "6172273586703700991",
    "arrow": "5244666105099723271",
}

def get_video_emoji(name: str) -> str:
    """Get the video emoji ID by its placeholder name."""
    return VIDEO_EMOJIS.get(name, "5431631484191612457")

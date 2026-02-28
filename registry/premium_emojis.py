"""
Auralyx Music — Premium Emoji Registry
Centralized storage for custom emoji IDs and themes.
"""

# Default Theme
CURRENT_THEME = "neon"

# ── HOW TO GET REAL CUSTOM EMOJI IDS ──────────
# 1. Forward an emoji to @ChatIDrobot OR use bot command /getid.
# 2. Copy the resulting numeric ID.
# 3. Paste it below as a string inside quotes.
# ──────────────────────────────────────────────

# Premium Emoji Themes
# Key: Placeholder name (e.g., {music})
# Value: Custom Emoji ID (String) or Unicode Fallback
THEMES = {
    "neon": {
        "music": "6093576514392037256",
        "video": "5244789697078634033",
        "bank": "6235253239080555488",
        "battle": "5244876756065721794",
        "admin": "6116370442702819766",
        "success": "5350633767314661730",
        "error": "6096056720566522801",
        "warning": "5204056798474019667",
        "info": "5377409491086089535",
        "stats": "📊",
        "ping": "🏓",
        "time": "🕒",
        "user": "👤",
        "group": "👥",
        "bullet": "•",
        "arrow": "╰",
        "header_start": "🎶",
        "header_end": "💖",
        "loading": "6172689880703833098",
        "process": "6172394919529813114",
        "search": "6118595158452735753",
    },
    "royal": {
        "music": "🎵",
        "bank": "🏦",
        "success": "✨",
        # Add more royal IDs here
    },
    "minimal": {
        "music": "🎧",
        # Add more minimal IDs here
    }
}

def get_emoji(name: str, theme: str = None) -> str:
    """Get emoji ID or fallback for a given name and theme."""
    target_theme = theme or CURRENT_THEME
    theme_data = THEMES.get(target_theme, THEMES["neon"])
    return theme_data.get(name, THEMES["neon"].get(name, "❓"))

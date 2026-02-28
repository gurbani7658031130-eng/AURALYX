"""
Auralyx Music — Configuration
Loads all settings from environment variables with strict validation.
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Telegram API ─────────────────────────────
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")

# ── MongoDB ──────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# ── Owner & Sudo ─────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Comma-separated list of sudo user IDs (owner is always sudo)
_sudo_raw = os.getenv("SUDO_USERS", "")
SUDO_USERS: set[int] = {OWNER_ID} if OWNER_ID else set()
if _sudo_raw:
    SUDO_USERS.update(int(x.strip()) for x in _sudo_raw.split(",") if x.strip().isdigit())

# ── Bot Info ─────────────────────────────────
BOT_NAME = os.getenv("BOT_NAME", "Auralyx Music")
BOT_USERNAME = os.getenv("BOT_USERNAME", "AuralyxXMusicBot")

# ── Log Channel ──────────────────────────────
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

# ── Playback Limits ──────────────────────────
MAX_DURATION = 3600  # 1 hour
IDLE_TIMEOUT = 600   # 10 minutes auto-leave
ENABLE_PREMIUM_EFFECTS = os.getenv("ENABLE_PREMIUM_EFFECTS", "False").lower() == "true"

# ── Economy ──────────────────────────────────
DAILY_AMOUNT = 1000
ROB_COOLDOWN = 120       # seconds
ROB_SUCCESS_RATE = 0.40  # 40%
ROB_MAX_STEAL = 0.30     # steal up to 30% of target wallet
KILL_COOLDOWN = 60       # seconds
KILL_SUCCESS_RATE = 0.55 # 55%
PROTECT_DURATION = 300   # 5 minutes

# ── Extreme Performance Mode ─────────────────
# Rejects requests completely if above MAX
MAX_CPU_PERCENT = int(os.getenv("MAX_CPU_PERCENT", "95"))
MAX_RAM_PERCENT = int(os.getenv("MAX_RAM_PERCENT", "95"))
# Slows down incoming messages (sleep delay) if above THROTTLE
AUTO_THROTTLE_THRESHOLD = int(os.getenv("THROTTLE_CPU", "80"))

# ── Logging ──────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ── Startup Validation ──────────────────────
def validate_config():
    """Crash early if critical env vars are missing."""
    errors = []
    if not API_ID:
        errors.append("API_ID is missing or 0")
    if not API_HASH:
        errors.append("API_HASH is missing")
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is missing")
    if not OWNER_ID:
        errors.append("OWNER_ID is missing or 0")
    if not SESSION_STRING:
        errors.append("SESSION_STRING is missing (run python gen_session.py)")

    if errors:
        for e in errors:
            logger.critical("CONFIG ERROR: %s", e)
        sys.exit(1)

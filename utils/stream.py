"""
Auralyx Music — Stream Pipeline
FFmpeg process tracker and cleanup for audio streaming.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Track active FFmpeg processes for cleanup on skip/stop
_active_ffmpeg: dict[int, asyncio.subprocess.Process] = {}


def _get_cache_path(chat_id: int) -> str:
    """Return the absolute path to the local raw stream file."""
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"stream_{chat_id}.raw")


async def start_ffmpeg_stream(chat_id: int, url: str):
    """Start an FFmpeg process to stream decodes to a local buffered file."""
    await kill_stream(chat_id)
    target = _get_cache_path(chat_id)
    
    # FFmpeg command to decode to raw s16le PCM (Telegram Standard)
    # We use a file-based buffer to bypass Windows pipe issues with legacy PyTgCalls.
    cmd = [
        "ffmpeg", "-re", "-i", url,
        "-f", "s16le", "-ac", "1", "-ar", "48000", "-acodec", "pcm_s16le",
        "-y", target
    ]
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        _active_ffmpeg[chat_id] = proc
        # Give FFmpeg a head start to fill some buffer
        await asyncio.sleep(1.5)
        return target
    except Exception as e:
        logger.error("Failed to start FFmpeg stream for %s: %s", chat_id, e)
        return None


async def kill_stream(chat_id: int):
    """Stop FFmpeg and delete the local buffer file."""
    proc = _active_ffmpeg.pop(chat_id, None)
    if proc:
        try:
            if proc.returncode is None:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    target = _get_cache_path(chat_id)
    if os.path.exists(target):
        try:
            os.remove(target)
        except Exception as e:
            logger.warning("Could not delete cache file %s: %s", target, e)


async def cleanup_all():
    """Kill all active FFmpeg processes and clear cache."""
    for chat_id in list(_active_ffmpeg.keys()):
        await kill_stream(chat_id)


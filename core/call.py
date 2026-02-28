"""
Auralyx Music - Voice Chat Call Manager
Creates and manages per-chat GroupCall instances so each group
gets its own independent voice chat stream.
"""

import asyncio
import logging
from types import MethodType

from pytgcalls import GroupCallFactory

from core.assistant import assistant

logger = logging.getLogger(__name__)


def _attach_legacy_api(gc):
    """
    Add legacy helper methods expected by existing plugins.
    This keeps the bot compatible across PyTgCalls API variants.
    """

    def _resolve_stream(stream, is_video=None):
        if isinstance(stream, str):
            return stream, bool(is_video)
        source = getattr(stream, "source", None) or getattr(stream, "path", None) or ""
        return source, bool(is_video)

    async def join_group_call(self, chat_id, stream, stream_type=None, is_video=None):
        source, use_video = _resolve_stream(stream, is_video)
        if not self.is_connected:
            await self.join(chat_id)
            await asyncio.sleep(1.2)  # allow participant state to propagate

        last_err = None
        for _ in range(3):
            try:
                if use_video:
                    await self.start_video(source, with_audio=True, repeat=False)
                else:
                    await self.start_audio(source, repeat=False)
                return
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.0)
        if last_err:
            raise last_err

    async def change_stream(self, chat_id, stream, is_video=None):
        source, use_video = _resolve_stream(stream, is_video)
        if not self.is_connected:
            await self.join(chat_id)
            await asyncio.sleep(1.2)

        last_err = None
        for _ in range(3):
            try:
                if use_video:
                    await self.start_video(source, with_audio=True, repeat=False)
                else:
                    await self.start_audio(source, repeat=False)
                return
            except Exception as e:
                last_err = e
                await asyncio.sleep(1.0)
        if last_err:
            raise last_err

    async def mute_stream(self, chat_id, mute=True):
        await self.set_audio_pause(bool(mute))

    async def leave_current_group_call(self):
        await self.leave()

    def _schedule(coro):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass

    def stop_playout(self):
        _schedule(self.stop_media())

    def pause_playout(self):
        _schedule(self.set_audio_pause(True))

    def resume_playout(self):
        _schedule(self.set_audio_pause(False))

    if not hasattr(gc, "join_group_call"):
        gc.join_group_call = MethodType(join_group_call, gc)
    if not hasattr(gc, "change_stream"):
        gc.change_stream = MethodType(change_stream, gc)
    if not hasattr(gc, "mute_stream"):
        gc.mute_stream = MethodType(mute_stream, gc)
    if not hasattr(gc, "leave_current_group_call"):
        gc.leave_current_group_call = MethodType(leave_current_group_call, gc)
    if not hasattr(gc, "stop_playout"):
        gc.stop_playout = MethodType(stop_playout, gc)
    if not hasattr(gc, "pause_playout"):
        gc.pause_playout = MethodType(pause_playout, gc)
    if not hasattr(gc, "resume_playout"):
        gc.resume_playout = MethodType(resume_playout, gc)


class CallManager:
    """Manages one GroupCall per chat for independent multi-group playback."""

    def __init__(self):
        self._calls: dict[int, object] = {}  # chat_id -> GroupCall
        self._factory = GroupCallFactory(
            assistant,
            mtproto_backend=GroupCallFactory.MTPROTO_CLIENT_TYPE.PYROGRAM,
        )

    def _get_or_create(self, chat_id: int):
        """Get existing call for chat, or create a new one."""
        if chat_id not in self._calls:
            gc = self._factory.get_group_call()
            _attach_legacy_api(gc)
            self._calls[chat_id] = gc
            logger.info("Created new GroupCall for chat %s", chat_id)
        return self._calls[chat_id]

    def get(self, chat_id: int):
        """Get the GroupCall for a specific chat."""
        return self._get_or_create(chat_id)

    def remove(self, chat_id: int):
        """Remove a chat's call instance (after leaving)."""
        self._calls.pop(chat_id, None)

    def is_connected(self, chat_id: int) -> bool:
        """Check if we're connected to a chat's voice chat."""
        gc = self._calls.get(chat_id)
        return gc is not None and gc.is_connected


# Global singleton
call_manager = CallManager()

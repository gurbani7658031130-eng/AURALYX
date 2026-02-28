"""
Auralyx Music — Target Resolution Utility
Shared helper for resolving a target user from reply, user ID, or @username.
Used across all commands that target a user.
"""

from pyrogram import Client
from pyrogram.types import Message


async def resolve_target(client: Client, message: Message, arg_offset: int = 1):
    """
    Resolve a target user from:
      1. Reply to a message (takes priority)
      2. First arg as user ID (numeric)
      3. First arg as @username

    Args:
        client: The Pyrogram client
        message: The incoming message
        arg_offset: Which command arg is the identifier (default: 1 = first arg)

    Returns:
        (user_id, display_name, extra_args) or (None, None, None) if not found.
        extra_args = remaining args after the identifier (e.g. reason, amount).
    """
    # Method 1: Reply
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        extra = " ".join(message.command[1:])  # All args are "extra" when replying
        return target.id, target.first_name, extra

    # Method 2: User ID or @username as argument
    if len(message.command) > arg_offset:
        identifier = message.command[arg_offset]
        extra = " ".join(message.command[arg_offset + 1:])

        # Try numeric ID
        try:
            user_id = int(identifier)
            try:
                user = await client.get_users(user_id)
                return user_id, user.first_name, extra
            except Exception:
                return user_id, str(user_id), extra
        except ValueError:
            pass

        # Try @username
        if identifier.startswith("@"):
            try:
                user = await client.get_users(identifier)
                return user.id, user.first_name, extra
            except Exception:
                await message.reply_text(f"• User `{identifier}` not found.", quote=True)
                return None, None, None

    return None, None, None

from __future__ import annotations

from typing import Any

OWNER_REQUIRED_MESSAGE = "This bot only works in Telegram groups where the owner is a member."
ACTIVE_OWNER_STATUSES = {"creator", "administrator", "member"}


async def owner_gate(update: Any, context: Any) -> None:
    owner_id = context.application.bot_data.get("owner_telegram_id")
    if owner_id is None:
        return

    chat = getattr(update, "effective_chat", None)
    if chat is None:
        await _reply_unauthorized(update)
        _stop_update()
    if getattr(chat, "id", None) == owner_id:
        return

    bot = getattr(context, "bot", None) or getattr(context.application, "bot", None)
    try:
        member = await bot.get_chat_member(chat.id, owner_id)
    except Exception:
        await _reply_unauthorized(update)
        _stop_update()
    if getattr(member, "status", None) not in ACTIVE_OWNER_STATUSES:
        await _reply_unauthorized(update)
        _stop_update()


async def _reply_unauthorized(update: Any) -> None:
    message = getattr(update, "message", None)
    if message is not None:
        await message.reply_text(OWNER_REQUIRED_MESSAGE)
        return
    query = getattr(update, "callback_query", None)
    if query is not None:
        await query.answer("Not authorized")
        await query.message.reply_text(OWNER_REQUIRED_MESSAGE)


def _stop_update() -> None:
    try:
        from telegram.ext import ApplicationHandlerStop
    except ImportError:  # pragma: no cover - unit tests run without needing PTB behavior.
        raise PermissionError(OWNER_REQUIRED_MESSAGE)
    raise ApplicationHandlerStop

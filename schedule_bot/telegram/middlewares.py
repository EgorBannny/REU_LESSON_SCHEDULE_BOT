"""Middleware бота."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from .. import db

logger = logging.getLogger(__name__)


class ChatMemberTrackerMiddleware(BaseMiddleware):
    """Запоминает всех, кто писал в групповой чат — только так бот вообще
    может кого-то тегать в /сбор: Telegram не даёт ботам получить список
    участников чата напрямую.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.chat.type in ("group", "supergroup") and event.from_user:
            pool = data.get("pool")
            user = event.from_user
            if pool is not None and not user.is_bot:
                display_name = user.full_name or user.username or str(user.id)
                try:
                    await db.upsert_chat_member(pool, event.chat.id, user.id, display_name, user.username)
                except Exception:
                    logger.exception("Не удалось запомнить участника чата %s", event.chat.id)
        return await handler(event, data)

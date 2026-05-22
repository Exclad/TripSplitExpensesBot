from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeMessage:
    text: str
    replies: list[dict[str, Any]] = field(default_factory=list)

    async def reply_text(self, text: str, **kwargs: Any) -> None:
        self.replies.append({"text": text, **kwargs})


@dataclass
class FakeCallbackQuery:
    data: str
    message: FakeMessage
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str = "") -> None:
        self.answers.append(text)


def fake_user(user_id: int = 101, username: str | None = "Alex", full_name: str = "Alex") -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=username, full_name=full_name, first_name=full_name, last_name=None)


def fake_message_update(text: str, chat_id: int = -100, user: Any | None = None) -> SimpleNamespace:
    message = FakeMessage(text=text)
    return SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=user or fake_user(),
    )


def fake_callback_update(data: str, chat_id: int = -100, user: Any | None = None) -> SimpleNamespace:
    message = FakeMessage(text="")
    query = FakeCallbackQuery(data=data, message=message)
    return SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=user or fake_user(),
    )


def fake_context(trip_repository: Any, member_repository: Any | None = None, **bot_data_items: Any) -> SimpleNamespace:
    bot_data = {"trip_repository": trip_repository}
    if member_repository is not None:
        bot_data["member_repository"] = member_repository
    bot_data.update(bot_data_items)
    return SimpleNamespace(application=SimpleNamespace(bot_data=bot_data))

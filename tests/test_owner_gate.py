from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.fakes import fake_callback_update, fake_message_update
from tripsplitexpenses.bot.auth import OWNER_REQUIRED_MESSAGE, owner_gate


class StopUpdate(Exception):
    pass


class FakeBot:
    def __init__(self, status: str | None = "member") -> None:
        self.status = status
        self.calls: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id: int, user_id: int):
        self.calls.append((chat_id, user_id))
        if self.status is None:
            raise RuntimeError("Telegram lookup failed")
        return SimpleNamespace(status=self.status)


def _context(owner_id: int | None, bot: FakeBot | None = None):
    return SimpleNamespace(
        bot=bot or FakeBot(),
        application=SimpleNamespace(bot_data={"owner_telegram_id": owner_id}),
    )


@pytest.fixture(autouse=True)
def stop_update(monkeypatch):
    def stop() -> None:
        raise StopUpdate

    monkeypatch.setattr("tripsplitexpenses.bot.auth._stop_update", stop)


async def test_owner_gate_allows_when_owner_setting_is_absent():
    update = fake_message_update("/help")
    context = _context(None)

    await owner_gate(update, context)

    assert update.message.replies == []


async def test_owner_gate_allows_group_where_owner_is_member():
    bot = FakeBot("member")
    update = fake_message_update("/help", chat_id=-100)

    await owner_gate(update, _context(12345, bot))

    assert bot.calls == [(-100, 12345)]
    assert update.message.replies == []


async def test_owner_gate_blocks_group_where_owner_is_not_member():
    update = fake_message_update("/help", chat_id=-100)

    with pytest.raises(StopUpdate):
        await owner_gate(update, _context(12345, FakeBot("left")))

    assert update.message.replies[0]["text"] == OWNER_REQUIRED_MESSAGE


async def test_owner_gate_blocks_callback_in_unauthorized_group():
    update = fake_callback_update("help:add", chat_id=-100)

    with pytest.raises(StopUpdate):
        await owner_gate(update, _context(12345, FakeBot(None)))

    assert update.callback_query.answers == ["Not authorized"]
    assert update.callback_query.message.replies[0]["text"] == OWNER_REQUIRED_MESSAGE

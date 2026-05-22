from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update
from tripsplitexpenses.bot.handlers.help import HELP_PAGES, help_callback, help_command


async def test_help_overview_is_compact_with_common_commands_and_task_buttons(trip_repository):
    update = fake_message_update("/help")

    await help_command(update, fake_context(trip_repository))

    reply = update.message.replies[0]
    text = reply["text"]
    assert "TripSplitExpenses help" in text
    assert "/add 25 lunch" in text
    assert "/balance" in text
    assert "/members claim" in text
    assert "/archive and /reopen" in text
    assert "multiple payers" in text
    assert "itemized" in text
    assert "rate overrides" in text
    buttons = [button.callback_data for row in reply["reply_markup"].inline_keyboard for button in row]
    assert buttons == ["help:add", "help:fix", "help:balances", "help:members", "help:end", "help:rates"]


async def test_help_overview_does_not_mention_infrastructure(trip_repository):
    update = fake_message_update("/help")

    await help_command(update, fake_context(trip_repository))

    text = update.message.replies[0]["text"].lower()
    assert "nas" not in text
    assert "local" not in text
    assert "private" not in text


async def test_help_callbacks_return_focused_pages(trip_repository):
    for page in HELP_PAGES:
        update = fake_callback_update(f"help:{page}")

        await help_callback(update, fake_context(trip_repository))

        assert update.callback_query.answers == ["Help"]
        assert update.callback_query.message.replies[0]["text"] == HELP_PAGES[page]
        assert update.callback_query.message.replies[0]["reply_markup"] is not None

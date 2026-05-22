from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update
from tripsplitexpenses.bot.copy import ARCHIVE_CONFIRM_MESSAGE, DUPLICATE_TRIP_MESSAGE, NEWTRIP_GUIDE_MESSAGE, REOPEN_CONFIRM_MESSAGE
from tripsplitexpenses.bot.handlers.trips import archive_command, newtrip, reopen_command, setup_message, start_setup, trip_callback, trip_status
from tripsplitexpenses.bot.menu import ADD_EXPENSE, BALANCES, EXPENSES, MEMBERS, PEOPLE, SETUP_TRIP, TRIP


async def test_newtrip_command_creates_trip_and_returns_join_button(trip_repository, member_repository):
    update = fake_message_update("/newtrip Demo Trip SGD")
    context = fake_context(trip_repository, member_repository)

    await newtrip(update, context)

    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    assert trip.name == "Demo Trip"
    assert "Trip created: Demo Trip" in update.message.replies[0]["text"]
    assert "Settlement currency: SGD" in update.message.replies[0]["text"]
    assert "Default expense currency: SGD" in update.message.replies[0]["text"]
    assert update.message.replies[0]["reply_markup"] is not None
    assert update.message.replies[1]["text"] == "Main buttons are ready."
    assert _keyboard_labels(update.message.replies[1]["reply_markup"]) == [
        ADD_EXPENSE,
        BALANCES,
        PEOPLE,
        EXPENSES,
        MEMBERS,
        TRIP,
    ]


async def test_newtrip_missing_fields_starts_guided_setup(trip_repository, member_repository):
    update = fake_message_update("/newtrip")

    await newtrip(update, fake_context(trip_repository, member_repository))

    assert update.message.replies[0]["text"] == "What should we call this trip?"
    assert update.message.replies[0]["reply_markup"] is not None


async def test_duplicate_newtrip_is_friendly(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    first = fake_message_update("/newtrip Demo Trip SGD")
    second = fake_message_update("/newtrip Korea 2025 SGD")

    await newtrip(first, context)
    await newtrip(second, context)

    assert second.message.replies[0]["text"] == DUPLICATE_TRIP_MESSAGE


async def test_trip_status_reads_persisted_state(trip_repository, member_repository):
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), fake_context(trip_repository, member_repository))
    update = fake_message_update("/trip")

    await trip_status(update, fake_context(trip_repository, member_repository))

    assert "Demo Trip" in update.message.replies[0]["text"]
    assert "Settlement currency: SGD" in update.message.replies[0]["text"]
    assert "Default expense currency: SGD" in update.message.replies[0]["text"]
    assert "Members: 0" in update.message.replies[0]["text"]


async def test_guided_setup_creates_trip_with_default_expense_currency(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await start_setup(fake_message_update("Set up trip"), context)
    await setup_message(fake_message_update("Korea 2026"), context)
    await setup_message(fake_message_update("SGD"), context)
    confirm_prompt = fake_message_update("KRW")
    await setup_message(confirm_prompt, context)

    assert "Who is coming?" in confirm_prompt.message.replies[0]["text"]

    members_prompt = fake_message_update("Alex, Sam")
    await setup_message(members_prompt, context)

    assert "Default expense currency: KRW" in members_prompt.message.replies[0]["text"]
    assert "Members: Alex, Sam" in members_prompt.message.replies[0]["text"]

    await trip_callback(fake_callback_update("trip:setup:confirm"), context)

    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    assert trip.name == "Korea 2026"
    assert trip.base_currency == "SGD"
    assert trip.default_expense_currency == "KRW"


async def test_archive_command_asks_for_confirmation(trip_repository, member_repository):
    trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    update = fake_message_update("/archive")

    await archive_command(update, fake_context(trip_repository, member_repository))

    reply = update.message.replies[0]
    assert reply["text"] == ARCHIVE_CONFIRM_MESSAGE
    assert [button.callback_data for row in reply["reply_markup"].inline_keyboard for button in row] == [
        "trip:archive:confirm",
        "trip:archive:cancel",
    ]


async def test_archive_confirm_marks_trip_read_only_but_trip_status_still_works(trip_repository, member_repository):
    trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    context = fake_context(trip_repository, member_repository)

    await trip_callback(fake_callback_update("trip:archive:confirm"), context)
    status_update = fake_message_update("/trip")
    await trip_status(status_update, context)

    assert trip_repository.get_active_trip(-100) is None
    assert "Status: Archived" in status_update.message.replies[0]["text"]
    assert SETUP_TRIP in _keyboard_labels(status_update.message.replies[0]["reply_markup"])


async def test_reopen_command_asks_for_confirmation_and_confirm_reopens(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=101)
    context = fake_context(trip_repository, member_repository)
    reopen_update = fake_message_update("/reopen")

    await reopen_command(reopen_update, context)
    await trip_callback(fake_callback_update("trip:reopen:confirm"), context)

    assert reopen_update.message.replies[0]["text"] == REOPEN_CONFIRM_MESSAGE
    assert trip_repository.get_active_trip(-100) is not None


def _keyboard_labels(markup):
    return [getattr(button, "text", button) for row in markup.keyboard for button in row]

from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update
from tripsplitexpenses.bot.copy import ARCHIVE_CONFIRM_MESSAGE, DUPLICATE_TRIP_MESSAGE, NEWTRIP_GUIDE_MESSAGE, REOPEN_CONFIRM_MESSAGE
from tripsplitexpenses.bot.handlers.trips import archive_command, newtrip, reopen_command, trip_callback, trip_status


async def test_newtrip_command_creates_trip_and_returns_join_button(trip_repository, member_repository):
    update = fake_message_update("/newtrip Demo Trip SGD")
    context = fake_context(trip_repository, member_repository)

    await newtrip(update, context)

    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    assert trip.name == "Demo Trip"
    assert "Trip created: Demo Trip (SGD)" in update.message.replies[0]["text"]
    assert update.message.replies[0]["reply_markup"] is not None


async def test_newtrip_missing_fields_returns_guided_prompt(trip_repository, member_repository):
    update = fake_message_update("/newtrip")

    await newtrip(update, fake_context(trip_repository, member_repository))

    assert update.message.replies[0]["text"] == NEWTRIP_GUIDE_MESSAGE


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
    assert "Base currency: SGD" in update.message.replies[0]["text"]
    assert "Members: 0" in update.message.replies[0]["text"]


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


async def test_reopen_command_asks_for_confirmation_and_confirm_reopens(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=101)
    context = fake_context(trip_repository, member_repository)
    reopen_update = fake_message_update("/reopen")

    await reopen_command(reopen_update, context)
    await trip_callback(fake_callback_update("trip:reopen:confirm"), context)

    assert reopen_update.message.replies[0]["text"] == REOPEN_CONFIRM_MESSAGE
    assert trip_repository.get_active_trip(-100) is not None

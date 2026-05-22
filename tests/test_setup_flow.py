from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update
from tripsplitexpenses.bot.handlers.navigation import text_router
from tripsplitexpenses.bot.handlers.trips import setup_message, trip_callback
from tripsplitexpenses.bot.menu import ADD_EXPENSE, BALANCES, EXPENSES, MEMBERS, PEOPLE, SETUP_TRIP, TRIP


async def test_setup_menu_walks_trip_name_base_and_country_currency(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)

    start = fake_message_update(SETUP_TRIP)
    await text_router(start, context)
    assert start.message.replies[0]["text"] == "What should we call this trip?"
    assert _is_force_reply(start.message.replies[0]["reply_markup"])

    name = fake_message_update("Korea 2026")
    await setup_message(name, context)
    assert "settlements" in name.message.replies[0]["text"]
    assert _is_force_reply(name.message.replies[0]["reply_markup"])

    base = fake_message_update("SGD")
    await setup_message(base, context)
    assert "expenses usually be in" in base.message.replies[0]["text"]
    assert _is_force_reply(base.message.replies[0]["reply_markup"])

    country = fake_message_update("KRW")
    await setup_message(country, context)
    assert "Who is coming?" in country.message.replies[0]["text"]
    assert _is_force_reply(country.message.replies[0]["reply_markup"])

    members = fake_message_update("Alex, Sam")
    await setup_message(members, context)
    assert "Create Korea 2026?" in members.message.replies[0]["text"]
    assert "Members: Alex, Sam" in members.message.replies[0]["text"]

    await trip_callback(fake_callback_update("trip:setup:confirm"), context)
    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    assert trip.default_expense_currency == "KRW"
    assert [member.display_name for member in member_repository.list_members(trip.id)] == ["Alex", "Sam"]


async def test_setup_confirm_shows_mapping_buttons_and_active_menu(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)

    await text_router(fake_message_update(SETUP_TRIP), context)
    await setup_message(fake_message_update("Korea 2026"), context)
    await setup_message(fake_message_update("SGD"), context)
    await setup_message(fake_message_update("KRW"), context)
    await setup_message(fake_message_update("Alex, Sam"), context)
    confirm = fake_callback_update("trip:setup:confirm")

    await trip_callback(confirm, context)

    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    mapping_reply = confirm.callback_query.message.replies[0]
    assert "Trip created: Korea 2026" in mapping_reply["text"]
    assert "Each person can tap their name" in mapping_reply["text"]
    assert [button.text for row in mapping_reply["reply_markup"].inline_keyboard for button in row] == [
        "Alex",
        "Sam",
        "Join this trip",
    ]
    menu_reply = confirm.callback_query.message.replies[1]
    assert menu_reply["text"] == "Main buttons are ready."
    assert _keyboard_labels(menu_reply["reply_markup"]) == [ADD_EXPENSE, BALANCES, PEOPLE, EXPENSES, MEMBERS, TRIP]


async def test_setup_menu_can_start_new_trip_after_archiving_old_trip(trip_repository, member_repository):
    old_trip = trip_repository.create_trip(-100, "Old Trip", "SGD", 101, default_expense_currency="KRW")
    trip_repository.archive_trip(old_trip.id, archived_by_telegram_id=101)
    context = fake_context(trip_repository, member_repository)

    start = fake_message_update(SETUP_TRIP)
    await text_router(start, context)
    assert start.message.replies[0]["text"] == "What should we call this trip?"

    await setup_message(fake_message_update("New Trip"), context)
    await setup_message(fake_message_update("SGD"), context)
    await setup_message(fake_message_update("KRW"), context)
    await setup_message(fake_message_update("Skip"), context)
    await trip_callback(fake_callback_update("trip:setup:confirm"), context)

    active_trip = trip_repository.get_active_trip(-100)
    assert active_trip is not None
    assert active_trip.name == "New Trip"


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True


def _keyboard_labels(markup):
    return [getattr(button, "text", button) for row in markup.keyboard for button in row]

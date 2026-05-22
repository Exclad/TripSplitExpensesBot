from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update
from tripsplitexpenses.bot.handlers.navigation import text_router
from tripsplitexpenses.bot.handlers.trips import setup_message, trip_callback
from tripsplitexpenses.bot.menu import SETUP_TRIP


async def test_setup_menu_walks_trip_name_base_and_country_currency(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)

    start = fake_message_update(SETUP_TRIP)
    await text_router(start, context)
    assert start.message.replies[0]["text"] == "What should we call this trip?"

    name = fake_message_update("Korea 2026")
    await setup_message(name, context)
    assert "settlements" in name.message.replies[0]["text"]

    base = fake_message_update("SGD")
    await setup_message(base, context)
    assert "expenses usually be in" in base.message.replies[0]["text"]

    country = fake_message_update("KRW")
    await setup_message(country, context)
    assert "Create Korea 2026?" in country.message.replies[0]["text"]

    await trip_callback(fake_callback_update("trip:setup:confirm"), context)
    trip = trip_repository.get_active_trip(-100)
    assert trip is not None
    assert trip.default_expense_currency == "KRW"

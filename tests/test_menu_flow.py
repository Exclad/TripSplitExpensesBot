from __future__ import annotations

from tests.fakes import fake_context, fake_message_update
from tripsplitexpenses.bot.handlers.navigation import text_router
from tripsplitexpenses.bot.handlers.trips import trip_status
from tripsplitexpenses.bot.menu import ADD_EXPENSE, BALANCES, EXPENSES, MEMBERS, PEOPLE, SETUP_TRIP, TRIP
from tripsplitexpenses.exchange import FixedExchangeRateProvider


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Korea 2026", "SGD", 101, default_expense_currency="KRW")
    alex = member_repository.join_from_telegram_user(trip.id, 101, "alex", "alex", 101)
    sam = member_repository.add_manual_member(trip.id, "sam", 101)
    return trip, alex, sam


async def test_missing_trip_menu_exposes_setup_button(trip_repository, member_repository):
    update = fake_message_update(SETUP_TRIP)

    await text_router(update, fake_context(trip_repository, member_repository))

    assert update.message.replies[0]["text"] == "What should we call this trip?"
    assert _keyboard_text(update.message.replies[0]["reply_markup"]) == [[SETUP_TRIP, "Help"]]


async def test_trip_status_exposes_active_menu(trip_repository, member_repository):
    _trip_with_members(trip_repository, member_repository)
    update = fake_message_update("/trip")

    await trip_status(update, fake_context(trip_repository, member_repository))

    keyboard = update.message.replies[0]["reply_markup"].keyboard
    assert _keyboard_text(update.message.replies[0]["reply_markup"]) == [[ADD_EXPENSE, BALANCES], [PEOPLE, EXPENSES], [MEMBERS, TRIP]]


async def test_menu_routes_to_balance_people_expenses_and_members(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=FixedExchangeRateProvider({}),
    )

    balance = fake_message_update(BALANCES)
    await text_router(balance, context)
    assert "Total spent: SGD 0.00" in balance.message.replies[0]["text"]

    people = fake_message_update(PEOPLE)
    await text_router(people, context)
    assert "Person breakdown" in people.message.replies[0]["text"]

    expenses = fake_message_update(EXPENSES)
    await text_router(expenses, context)
    assert "Expenses" in expenses.message.replies[0]["text"]

    members = fake_message_update(MEMBERS)
    await text_router(members, context)
    assert "Members" in members.message.replies[0]["text"]


def _keyboard_text(markup):
    return [[getattr(button, "text", button) for button in row] for row in markup.keyboard]

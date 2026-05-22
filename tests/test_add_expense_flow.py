from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.copy import ARCHIVED_TRIP_READ_ONLY_MESSAGE
from tripsplitexpenses.bot.handlers.expenses import add_expense, expense_callback
from tripsplitexpenses.categories import BUILT_IN_CATEGORIES
from tripsplitexpenses.exchange import FixedExchangeRateProvider


def _context(trip_repository, member_repository, expense_repository, provider=None):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=provider or FixedExchangeRateProvider({}),
    )


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    Alex = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 101)
    return trip, Alex, Sam


async def test_add_quick_start_prompts_for_category(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    update = fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex"))

    await add_expense(update, _context(trip_repository, member_repository, expense_repository))

    assert update.message.replies[0]["text"] == "Pick a category."
    buttons = update.message.replies[0]["reply_markup"].inline_keyboard
    assert [row[0].text for row in buttons] == list(BUILT_IN_CATEGORIES) + ["+ Custom"]


async def test_add_without_args_starts_guided_expense_flow(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    update = fake_message_update("/add")

    await add_expense(update, _context(trip_repository, member_repository, expense_repository))

    assert update.message.replies[0]["text"] == "How much was it? I will use SGD."


async def test_equal_split_save_persists_expense_and_posts_saved_card(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    category_update = fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(category_update, context)
    save_update = fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(save_update, context)

    expenses = expense_repository.list_expenses(trip.id)
    assert len(expenses) == 1
    assert expenses[0].description == "lunch"
    assert len(expenses[0].splits) == 2
    assert "Saved: lunch - SGD 25.00" in save_update.callback_query.message.replies[0]["text"]
    assert save_update.callback_query.message.replies[0]["reply_markup"] is not None


async def test_foreign_currency_confirmation_shows_base_equivalent(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("JPY", "SGD", date.today().isoformat()): Decimal("0.0089")})
    context = _context(trip_repository, member_repository, expense_repository, provider)
    await add_expense(fake_message_update("/add 1930 JPY ramen", user=fake_user(101, "Alex", "Alex")), context)
    category_update = fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(category_update, context)

    assert "JPY 1,930 (~SGD 17.18)" in category_update.callback_query.message.replies[0]["text"]


async def test_add_expense_blocks_archived_trip_with_read_only_copy(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=101)
    update = fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex"))

    await add_expense(update, _context(trip_repository, member_repository, expense_repository))

    assert update.message.replies[0]["text"] == ARCHIVED_TRIP_READ_ONLY_MESSAGE


async def test_add_expense_defaults_payer_to_mapped_manual_member(trip_repository, member_repository, expense_repository):
    trip, _, Sam = _trip_with_members(trip_repository, member_repository)
    member_repository.map_manual_member_to_telegram(Sam.id, 202, "Sam", 101)
    context = _context(trip_repository, member_repository, expense_repository)

    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(202, "Sam", "Sam Real")), context)

    draft = context.application.bot_data["expense_drafts"][(-100, 202)]
    assert draft["payer_member_id"] == Sam.id
    assert draft["payer_name"] == "Sam"

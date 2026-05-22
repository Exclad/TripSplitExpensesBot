from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.copy import ARCHIVED_TRIP_READ_ONLY_MESSAGE
from tripsplitexpenses.bot.handlers.balances import balance_command
from tripsplitexpenses.bot.handlers.expenses import add_expense, exact_amount_message, expense_callback
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


async def _saved_foreign_expense(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("JPY", "SGD", date.today().isoformat()): Decimal("0.0089")})
    context = _context(trip_repository, member_repository, expense_repository, provider)
    await add_expense(fake_message_update("/add 1930 JPY ramen", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    return trip, context, expense_repository.list_expenses(trip.id)[0]


async def test_conversion_failure_offers_manual_override_options(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    update = fake_message_update("/add 1930 JPY ramen", user=fake_user(101, "Alex", "Alex"))

    await add_expense(update, _context(trip_repository, member_repository, expense_repository))

    reply = update.message.replies[0]
    assert "I could not find an exchange rate" in reply["text"]
    assert [button.text for row in reply["reply_markup"].inline_keyboard for button in row] == ["Enter rate", "Enter trip amount"]


async def test_entry_manual_rate_continues_to_category_picker(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 1930 JPY ramen", user=fake_user(101, "Alex", "Alex")), context)
    rate_prompt = fake_callback_update("expense:override-rate", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(rate_prompt, context)
    assert _is_force_reply(rate_prompt.callback_query.message.replies[0]["reply_markup"])
    message = fake_message_update("0.008912", user=fake_user(101, "Alex", "Alex"))

    await exact_amount_message(message, context)

    draft = context.application.bot_data["expense_drafts"][(-100, 101)]
    assert draft["base_money"].amount_minor == 1720
    assert draft["exchange_rate"].provider == "manual-rate"
    assert message.message.replies[0]["text"] == "Pick a category."


async def test_entry_exact_base_equivalent_continues_to_category_picker(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 1930 JPY ramen", user=fake_user(101, "Alex", "Alex")), context)
    amount_prompt = fake_callback_update("expense:override-equivalent", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(amount_prompt, context)
    assert _is_force_reply(amount_prompt.callback_query.message.replies[0]["reply_markup"])
    message = fake_message_update("17.20", user=fake_user(101, "Alex", "Alex"))

    await exact_amount_message(message, context)

    draft = context.application.bot_data["expense_drafts"][(-100, 101)]
    assert draft["base_money"].amount_minor == 1720
    assert draft["exchange_rate"].provider == "manual-equivalent"


async def test_saved_details_exposes_override_rate_button(trip_repository, member_repository, expense_repository):
    _, context, expense = await _saved_foreign_expense(trip_repository, member_repository, expense_repository)
    details = fake_callback_update(f"expense:details:{expense.id}", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(details, context)

    buttons = details.callback_query.message.replies[0]["reply_markup"].inline_keyboard
    assert buttons[0][0].text == "Override rate"
    assert buttons[0][0].callback_data == f"expense:override-rate:{expense.id}"


async def test_after_save_override_updates_details_and_balance_totals(trip_repository, member_repository, expense_repository):
    trip, context, expense = await _saved_foreign_expense(trip_repository, member_repository, expense_repository)
    override_prompt = fake_callback_update(f"expense:override-rate:{expense.id}", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(override_prompt, context)
    assert _is_force_reply(override_prompt.callback_query.message.replies[0]["reply_markup"])
    await exact_amount_message(fake_message_update("0.008912", user=fake_user(101, "Alex", "Alex")), context)

    updated = expense_repository.get_expense(expense.id)
    assert updated.base_amount_minor == 1720
    details = fake_callback_update(f"expense:details:{expense.id}", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(details, context)
    assert "Manual override: yes" in details.callback_query.message.replies[0]["text"]
    assert "Rate overridden" in details.callback_query.message.replies[0]["text"]

    balance = fake_message_update("/balance")
    await balance_command(balance, context)
    assert "Total spent: SGD 17.20" in balance.message.replies[0]["text"]


async def test_archived_trip_blocks_saved_rate_override(trip_repository, member_repository, expense_repository):
    trip, context, expense = await _saved_foreign_expense(trip_repository, member_repository, expense_repository)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=101)
    update = fake_callback_update(f"expense:override-rate:{expense.id}", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(update, context)

    assert update.callback_query.message.replies[0]["text"] == ARCHIVED_TRIP_READ_ONLY_MESSAGE


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

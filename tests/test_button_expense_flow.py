from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.handlers.expenses import exact_amount_message, expense_callback, start_button_expense
from tripsplitexpenses.exchange import FixedExchangeRateProvider


def _context(trip_repository, member_repository, expense_repository, provider=None):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=provider or FixedExchangeRateProvider({}),
    )


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Korea 2026", "SGD", 101, default_expense_currency="KRW")
    alex = member_repository.join_from_telegram_user(trip.id, 101, "alex", "alex", 101)
    sam = member_repository.add_manual_member(trip.id, "sam", 101)
    return trip, alex, sam


async def test_button_expense_defaults_to_country_currency_and_saves(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("KRW", "SGD", date.today().isoformat()): Decimal("0.001")})
    context = _context(trip_repository, member_repository, expense_repository, provider)

    start = fake_message_update("Add expense", user=fake_user(101, "alex", "alex"))
    await start_button_expense(start, context)

    assert "I will use KRW" in start.message.replies[0]["text"]
    assert start.message.replies[0]["reply_markup"].inline_keyboard[0][0].text == "Use SGD instead"
    assert start.message.replies[1]["text"] == "Send the amount in KRW."
    assert _is_force_reply(start.message.replies[1]["reply_markup"])

    amount = fake_message_update("3500", user=fake_user(101, "alex", "alex"))
    await exact_amount_message(amount, context)
    assert amount.message.replies[0]["text"] == "What was it for?"
    assert _is_force_reply(amount.message.replies[0]["reply_markup"])

    description = fake_message_update("lunch", user=fake_user(101, "alex", "alex"))
    await exact_amount_message(description, context)
    assert description.message.replies[0]["text"] == "Pick a category."

    category = fake_callback_update("expense:category:Food", user=fake_user(101, "alex", "alex"))
    await expense_callback(category, context)
    assert category.callback_query.message.replies[0]["text"] == "Who should split this?"

    done = fake_callback_update("expense:split-done", user=fake_user(101, "alex", "alex"))
    await expense_callback(done, context)
    assert "KRW 3,500.00 (~SGD 3.50)" in done.callback_query.message.replies[0]["text"]

    save = fake_callback_update("expense:save", user=fake_user(101, "alex", "alex"))
    await expense_callback(save, context)

    expense = expense_repository.list_expenses(trip.id)[0]
    assert expense.original_currency == "KRW"
    assert expense.base_currency == "SGD"
    assert expense.base_amount_minor == 350


async def test_split_member_toggle_edits_existing_selector_message(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("KRW", "SGD", date.today().isoformat()): Decimal("0.001")})
    context = _context(trip_repository, member_repository, expense_repository, provider)

    await start_button_expense(fake_message_update("Add expense", user=fake_user(101, "alex", "alex")), context)
    await exact_amount_message(fake_message_update("3500", user=fake_user(101, "alex", "alex")), context)
    await exact_amount_message(fake_message_update("lunch", user=fake_user(101, "alex", "alex")), context)
    category = fake_callback_update("expense:category:Food", user=fake_user(101, "alex", "alex"))
    await expense_callback(category, context)
    selector = category.callback_query.message.replies[0]["reply_markup"]
    sam_button = selector.inline_keyboard[1][0]

    toggle = fake_callback_update(sam_button.callback_data, user=fake_user(101, "alex", "alex"))
    await expense_callback(toggle, context)

    assert toggle.callback_query.message.replies == []
    assert toggle.callback_query.message.edits[0]["text"] == "Who should split this?"
    updated_buttons = toggle.callback_query.message.edits[0]["reply_markup"].inline_keyboard
    assert updated_buttons[0][0].text == "✓ alex"
    assert updated_buttons[1][0].text == "sam"


async def test_button_expense_can_switch_to_base_currency_before_amount(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)

    await start_button_expense(fake_message_update("Add expense", user=fake_user(101, "alex", "alex")), context)
    switch = fake_callback_update("expense:use-base-currency", user=fake_user(101, "alex", "alex"))
    await expense_callback(switch, context)

    assert "send the amount in SGD" in switch.callback_query.message.replies[0]["text"]
    assert _is_force_reply(switch.callback_query.message.replies[0]["reply_markup"])

    amount = fake_message_update("12.50", user=fake_user(101, "alex", "alex"))
    await exact_amount_message(amount, context)

    draft = context.application.bot_data["expense_drafts"][(-100, 101)]
    assert draft["original_money"].currency == "SGD"
    assert draft["base_money"].amount_minor == 1250


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

from __future__ import annotations

from decimal import Decimal

from tripsplitexpenses.bot.copy import MISSING_TRIP_MESSAGE
from tripsplitexpenses.bot.handlers.balances import balance_callback, balance_command
from tripsplitexpenses.exchange import FixedExchangeRateProvider, convert_money
from tripsplitexpenses.money import parse_money
from tests.fakes import fake_callback_update, fake_context, fake_message_update


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    alex = member_repository.add_manual_member(trip.id, "Alex", 42)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 42)
    Alex = member_repository.add_manual_member(trip.id, "Taylor", 42)
    return trip, alex, Sam, Alex


def _context(trip_repository, member_repository, expense_repository):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
    )


def _save_equal_expense(
    expense_repository,
    trip,
    payer,
    split_members,
    *,
    description="hotel",
    category="Stay",
    amount="90.00",
    currency="SGD",
    expense_date="2026-05-21",
    rate_value="1",
):
    money = parse_money(amount, currency)
    provider = FixedExchangeRateProvider({(currency, trip.base_currency, expense_date): Decimal(rate_value)})
    base, rate = convert_money(money, trip.base_currency, expense_date, provider)
    return expense_repository.create_expense(
        trip_id=trip.id,
        description=description,
        category=category,
        expense_date=expense_date,
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=payer.id,
        split_member_ids=[member.id for member in split_members],
        created_by_telegram_id=42,
    )


async def test_balance_without_trip_uses_missing_trip_message(trip_repository):
    update = fake_message_update("/balance")
    context = fake_context(trip_repository)

    await balance_command(update, context)

    assert update.message.replies[0]["text"] == MISSING_TRIP_MESSAGE


async def test_balance_empty_trip_is_friendly(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    update = fake_message_update("/balance")
    context = fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
    )

    await balance_command(update, context)

    text = update.message.replies[0]["text"]
    assert "No expenses yet." in text
    assert "Total spent: SGD 0.00" in text


async def test_balance_still_works_for_archived_trip(trip_repository, member_repository, expense_repository):
    trip, _, _, _ = _trip_with_members(trip_repository, member_repository)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=42)
    update = fake_message_update("/balance")

    await balance_command(update, _context(trip_repository, member_repository, expense_repository))

    assert "No expenses yet." in update.message.replies[0]["text"]
    assert "Total spent: SGD 0.00" in update.message.replies[0]["text"]


async def test_balance_summary_is_settlement_first_with_buttons(trip_repository, member_repository, expense_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    _save_equal_expense(expense_repository, trip, Alex, [alex, Sam, Alex])
    context = _context(trip_repository, member_repository, expense_repository)
    update = fake_message_update("/balance")

    await balance_command(update, context)

    reply = update.message.replies[0]
    text = reply["text"]
    assert text.index("Settle up") < text.index("Total spent: SGD 90.00")
    assert "Alex pays Taylor SGD 30.00" in text
    assert "Sam pays Taylor SGD 30.00" in text
    assert "Taylor should receive SGD 60.00" in text
    assert "Alex owes SGD 30.00" in text
    buttons = reply["reply_markup"].inline_keyboard
    assert [button.text for row in buttons for button in row] == [
        "Person breakdown",
        "Category breakdown",
        "Expense list",
        "Audit",
    ]
    assert [button.callback_data for row in buttons for button in row] == [
        "balance:people",
        "balance:categories",
        "balance:expenses:0",
        "balance:audit",
    ]


async def test_person_breakdown_callback_shows_paid_consumed_owes_and_is_owed(trip_repository, member_repository, expense_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    _save_equal_expense(expense_repository, trip, Alex, [alex, Sam, Alex])
    update = fake_callback_update("balance:people")

    await balance_callback(update, _context(trip_repository, member_repository, expense_repository))

    text = update.callback_query.message.replies[0]["text"]
    assert "Person breakdown" in text
    assert "Taylor" in text
    assert "Paid: SGD 0.00" in text
    assert "Consumed: SGD 30.00" in text
    assert "Owes: SGD 30.00" in text
    assert "Alex" in text
    assert "Paid: SGD 90.00" in text
    assert "Is owed: SGD 60.00" in text


async def test_category_breakdown_callback_groups_base_currency_totals(trip_repository, member_repository, expense_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    _save_equal_expense(expense_repository, trip, Alex, [alex, Sam, Alex], category="Food", amount="10.00")
    _save_equal_expense(expense_repository, trip, alex, [alex, Sam, Alex], category="Transit", amount="5.00")
    update = fake_callback_update("balance:categories")

    await balance_callback(update, _context(trip_repository, member_repository, expense_repository))

    text = update.callback_query.message.replies[0]["text"]
    assert "Category breakdown" in text
    assert "- Food: SGD 10.00" in text
    assert "- Transit: SGD 5.00" in text


async def test_expense_list_callback_pages_newest_first_with_required_row_context(trip_repository, member_repository, expense_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    for index in range(11):
        _save_equal_expense(
            expense_repository,
            trip,
            Alex,
            [alex, Sam, Alex],
            description=f"expense-{index:02d}",
            category="Food",
            amount=f"{index + 1}.00",
            expense_date=f"2026-05-{index + 1:02d}",
        )

    first_page = fake_callback_update("balance:expenses:0")
    await balance_callback(first_page, _context(trip_repository, member_repository, expense_repository))

    first_reply = first_page.callback_query.message.replies[0]
    assert "Expenses 1-10 of 11" in first_reply["text"]
    assert "expense-10" in first_reply["text"]
    assert "2026-05-11 - Food - SGD 11.00 - paid by Taylor - split 3 ways" in first_reply["text"]
    assert "expense-00" not in first_reply["text"]
    assert first_reply["reply_markup"].inline_keyboard[0][0].callback_data == "balance:expenses:10"

    second_page = fake_callback_update("balance:expenses:10")
    await balance_callback(second_page, _context(trip_repository, member_repository, expense_repository))

    second_reply = second_page.callback_query.message.replies[0]
    assert "Expenses 11-11 of 11" in second_reply["text"]
    assert "expense-00" in second_reply["text"]
    assert "reply_markup" not in second_reply


async def test_audit_callback_starts_by_person_and_person_audit_explains_rows(trip_repository, member_repository, expense_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    original = _save_equal_expense(
        expense_repository,
        trip,
        Alex,
        [alex, Sam, Alex],
        description="ramen",
        category="Food",
        amount="1930",
        currency="JPY",
        rate_value="0.0089",
    )
    money = parse_money("1.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-21", FixedExchangeRateProvider({}))
    expense_repository.create_refund(
        original_expense_id=original.id,
        recipient_member_id=Sam.id,
        amount_minor=money.amount_minor,
        currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        expense_date="2026-05-21",
        created_by_telegram_id=42,
    )
    correction_money = parse_money("0.50", "SGD")
    correction_base, correction_rate = convert_money(correction_money, "SGD", "2026-05-21", FixedExchangeRateProvider({}))
    expense_repository.create_correction(
        original_expense_id=original.id,
        amount_minor=correction_money.amount_minor,
        currency=correction_money.currency,
        base_amount_minor=correction_base.amount_minor,
        base_currency=correction_base.currency,
        exchange_rate=correction_rate,
        expense_date="2026-05-21",
        note="rounding fix",
        member_id=Sam.id,
        created_by_telegram_id=42,
    )

    audit_menu = fake_callback_update("balance:audit")
    await balance_callback(audit_menu, _context(trip_repository, member_repository, expense_repository))

    menu_reply = audit_menu.callback_query.message.replies[0]
    assert "Audit by person" in menu_reply["text"]
    assert [button.text for row in menu_reply["reply_markup"].inline_keyboard for button in row] == ["Alex", "Sam", "Taylor"]

    person_audit = fake_callback_update(f"balance:audit-person:{Sam.id}")
    await balance_callback(person_audit, _context(trip_repository, member_repository, expense_repository))

    text = person_audit.callback_query.message.replies[0]["text"]
    assert "Why Sam owes" in text
    assert "Paid minus consumed" in text
    assert "Paid: SGD -0.50" in text
    assert "Consumed: SGD 5.23" in text
    assert "JPY 1,930 (~SGD 17.18)" in text
    assert "Rate: 1 JPY = 0.0089 SGD on 2026-05-21" in text
    assert "Refund:" in text
    assert "Correction:" in text
    assert "Split cents were assigned consistently so totals match." in text

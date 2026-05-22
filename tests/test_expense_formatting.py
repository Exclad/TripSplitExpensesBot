from __future__ import annotations

from decimal import Decimal

from tripsplitexpenses.bot.formatters import format_amount_pair, format_confirmation, format_exchange_details, format_saved_expense
from tripsplitexpenses.exchange import ExchangeRate
from tripsplitexpenses.money import Money
from tripsplitexpenses.repositories.expenses import Expense, ExpensePayer, ExpenseSplit


def test_amount_pair_shows_original_plus_base_for_foreign_currency():
    assert format_amount_pair(Money(193000, "JPY"), Money(1718, "SGD")) == "JPY 1,930 (~SGD 17.18)"


def test_confirmation_is_compact_receipt(member_repository, trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    Alex = member_repository.add_manual_member(trip.id, "Alex", 42)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 42)
    draft = {
        "description": "lunch",
        "original_money": Money(2500, "SGD"),
        "base_money": Money(2500, "SGD"),
        "category": "Food",
        "expense_date": "2026-05-20",
        "payer_name": "Alex",
        "split_method": "equal",
        "split_member_ids": [Alex.id, Sam.id],
    }

    text = format_confirmation(draft, [Alex, Sam])

    assert "Ready to save?" in text
    assert "lunch - SGD 25.00" in text
    assert "Food" in text
    assert "Alex, Sam" in text


def test_saved_expense_card_is_compact():
    expense = Expense(
        id="e1",
        trip_id="t1",
        description="ramen",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=193000,
        original_currency="JPY",
        base_amount_minor=1718,
        base_currency="SGD",
        exchange_rate=Decimal("0.0089"),
        exchange_rate_date="2026-05-20",
        exchange_rate_provider="fixed",
        created_at="now",
        updated_at="now",
        created_by_telegram_id=42,
        payers=[ExpensePayer("m1", 193000, "JPY")],
        splits=[ExpenseSplit("m1", 859, "SGD"), ExpenseSplit("m2", 859, "SGD")],
    )

    assert "Saved: ramen - JPY 1,930 (~SGD 17.18)" in format_saved_expense(expense, "Alex", 2)
    assert "split 2 ways" in format_saved_expense(expense, "Alex", 2)


def test_exchange_details_include_rate_date_and_source():
    expense = Expense(
        id="e1",
        trip_id="t1",
        description="ramen",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=193000,
        original_currency="JPY",
        base_amount_minor=1718,
        base_currency="SGD",
        exchange_rate=Decimal("0.0089"),
        exchange_rate_date="2026-05-20",
        exchange_rate_provider="fixed",
        created_at="now",
        updated_at="now",
        created_by_telegram_id=42,
        payers=[],
        splits=[],
    )

    text = format_exchange_details(expense)

    assert "Rate: 1 JPY = 0.0089 SGD" in text
    assert "Rate date: 2026-05-20" in text
    assert "Source: fixed" in text

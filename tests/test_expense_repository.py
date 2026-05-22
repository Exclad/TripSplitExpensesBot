from __future__ import annotations

from decimal import Decimal

import pytest

from tripsplitexpenses.db.connection import connect
from tripsplitexpenses.db.migrations import run_migrations
from tripsplitexpenses.exchange import FixedExchangeRateProvider, convert_money, convert_with_manual_rate
from tripsplitexpenses.money import MoneyError, parse_money
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.repositories.members import MemberRepository
from tripsplitexpenses.repositories.trips import TripRepository


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    Alex = member_repository.add_manual_member(trip.id, "Alex", 42)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 42)
    return trip, Alex, Sam


def _save_equal_expense(expense_repository, trip, Alex, Sam, *, created_by=42):
    money = parse_money("25.00", "SGD")
    base, rate = convert_money(money, trip.base_currency, "2026-05-20", FixedExchangeRateProvider({}))
    return expense_repository.create_expense(
        trip_id=trip.id,
        description="lunch",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=created_by,
        actor_display_name="Alex",
    )


def test_create_equal_split_expense(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("25.00", "SGD")
    base, rate = convert_money(money, trip.base_currency, "2026-05-20", FixedExchangeRateProvider({}))

    expense = expense_repository.create_expense(
        trip_id=trip.id,
        description="lunch",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )

    assert expense.description == "lunch"
    assert expense.category == "Food"
    assert expense.original_amount_minor == 2500
    assert expense.base_amount_minor == 2500
    assert expense.exchange_rate == Decimal("1")
    assert len(expense.payers) == 1
    assert sum(split.amount_minor for split in expense.splits) == 2500


def test_create_multiple_payer_expense(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("35.03", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))

    expense = expense_repository.create_expense(
        trip_id=trip.id,
        description="dinner",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_shares={Alex.id: 2016, Sam.id: 1487},
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )

    assert sorted(payer.amount_minor for payer in expense.payers) == [1487, 2016]


def test_multiple_payer_mismatch_is_rejected(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("35.03", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))

    with pytest.raises(MoneyError, match="Payer total does not match"):
        expense_repository.create_expense(
            trip_id=trip.id,
            description="dinner",
            category="Food",
            expense_date="2026-05-20",
            split_method="equal",
            original_amount_minor=money.amount_minor,
            original_currency=money.currency,
            base_amount_minor=base.amount_minor,
            base_currency=base.currency,
            exchange_rate=rate,
            payer_shares={Alex.id: 2016, Sam.id: 1486},
            split_member_ids=[Alex.id, Sam.id],
            created_by_telegram_id=42,
        )


def test_create_itemized_expense_with_shared_charge(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("31.01", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))

    expense = expense_repository.create_expense(
        trip_id=trip.id,
        description="restaurant",
        category="Food",
        expense_date="2026-05-20",
        split_method="itemized",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        itemized_lines=[
            {"name": "ramen", "base_amount_minor": 2000, "member_ids": [Alex.id]},
            {"name": "tea", "base_amount_minor": 1000, "member_ids": [Sam.id]},
        ],
        shared_charges=[{"name": "service", "base_amount_minor": 101}],
        created_by_telegram_id=42,
    )

    assert len(expense.line_items) == 2
    assert len(expense.shared_charges) == 1
    assert sum(split.amount_minor for split in expense.splits) == 3101
    assert {split.member_id: split.amount_minor for split in expense.splits} == {Alex.id: 2068, Sam.id: 1033}


def test_linked_refund_and_correction_entries_affect_total(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("25.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))
    original = expense_repository.create_expense(
        trip_id=trip.id,
        description="lunch",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )

    refund = expense_repository.create_refund(
        original_expense_id=original.id,
        recipient_member_id=Sam.id,
        amount_minor=500,
        currency="SGD",
        base_amount_minor=500,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-21",
        created_by_telegram_id=42,
    )
    correction = expense_repository.create_correction(
        original_expense_id=original.id,
        amount_minor=100,
        currency="SGD",
        base_amount_minor=100,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-21",
        note="extra sauce",
        member_id=Alex.id,
        created_by_telegram_id=42,
    )

    assert refund.entry_type == "refund"
    assert correction.entry_type == "correction"
    assert refund.linked_expense_id == original.id
    assert expense_repository.total_spent_minor(trip.id) == 2100


def test_soft_delete_hides_expense_from_lists_and_totals(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("25.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))
    saved = expense_repository.create_expense(
        trip_id=trip.id,
        description="lunch",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )

    expense_repository.delete_expense(saved.id, 99)

    assert expense_repository.get_expense(saved.id) is None
    assert expense_repository.list_expenses(trip.id) == []
    assert expense_repository.total_spent_minor(trip.id) == 0


def test_create_foreign_currency_expense_preserves_original_and_base_amount(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("JPY", "SGD", "2026-05-20"): "0.0089"})
    money = parse_money("1930", "JPY")
    base, rate = convert_money(money, trip.base_currency, "2026-05-20", provider)

    expense = expense_repository.create_expense(
        trip_id=trip.id,
        description="ramen",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )

    assert expense.original_currency == "JPY"
    assert expense.original_amount_minor == 193000
    assert expense.base_currency == "SGD"
    assert expense.base_amount_minor == 1718
    assert expense.exchange_rate_provider == "fixed"


def test_exact_split_mismatch_is_rejected(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    money = parse_money("10.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))

    with pytest.raises(MoneyError, match="Split total does not match"):
        expense_repository.create_expense(
            trip_id=trip.id,
            description="snacks",
            category="Food",
            expense_date="2026-05-20",
            split_method="exact",
            original_amount_minor=money.amount_minor,
            original_currency=money.currency,
            base_amount_minor=base.amount_minor,
            base_currency=base.currency,
            exchange_rate=rate,
            payer_member_id=Alex.id,
            exact_shares={Alex.id: 500, Sam.id: 499},
            created_by_telegram_id=42,
        )


def test_expense_persists_after_reopened_connection(tmp_path):
    database_path = tmp_path / "expenses.sqlite3"
    first = connect(database_path)
    run_migrations(first)
    trip_repo = TripRepository(first)
    member_repo = MemberRepository(first)
    expense_repo = ExpenseRepository(first)
    trip, Alex, Sam = _trip_with_members(trip_repo, member_repo)
    money = parse_money("25.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-20", FixedExchangeRateProvider({}))
    saved = expense_repo.create_expense(
        trip_id=trip.id,
        description="lunch",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )
    first.close()

    second = connect(database_path)
    run_migrations(second)
    try:
        reopened = ExpenseRepository(second).get_expense(saved.id)
        assert reopened is not None
        assert reopened.description == "lunch"
        assert sum(split.amount_minor for split in reopened.splits) == 2500
    finally:
        second.close()


def test_create_expense_writes_created_audit_event(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)

    expense = _save_equal_expense(expense_repository, trip, Alex, Sam)

    events = expense_repository.list_audit_events(expense.id)
    assert [event.event_type for event in events] == ["created"]
    assert events[0].actor_telegram_id == 42
    assert events[0].summary == "Expense created."


def test_update_simple_field_writes_edited_event_with_before_after(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    expense = _save_equal_expense(expense_repository, trip, Alex, Sam)

    expense_repository.update_expense(expense.id, description="brunch", updated_by_telegram_id=99, actor_display_name="Friend")

    events = expense_repository.list_audit_events(expense.id)
    edited = events[-1]
    assert edited.event_type == "edited"
    assert edited.field_name == "description"
    assert edited.old_value == "lunch"
    assert edited.new_value == "brunch"
    assert edited.actor_display_name == "Friend"


def test_delete_preserves_retrievable_audit_history(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    expense = _save_equal_expense(expense_repository, trip, Alex, Sam)

    expense_repository.delete_expense(expense.id, 99, actor_display_name="Friend")

    assert expense_repository.get_expense(expense.id) is None
    events = expense_repository.list_audit_events(expense.id)
    assert [event.event_type for event in events] == ["created", "deleted"]
    assert events[-1].actor_telegram_id == 99


def test_refund_and_correction_write_events_on_original_expense(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    expense = _save_equal_expense(expense_repository, trip, Alex, Sam)
    _, rate = convert_money(parse_money("1.00", "SGD"), "SGD", "2026-05-21", FixedExchangeRateProvider({}))

    refund = expense_repository.create_refund(
        original_expense_id=expense.id,
        recipient_member_id=Sam.id,
        amount_minor=100,
        currency="SGD",
        base_amount_minor=100,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-21",
        created_by_telegram_id=42,
    )
    correction = expense_repository.create_correction(
        original_expense_id=expense.id,
        amount_minor=50,
        currency="SGD",
        base_amount_minor=50,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-21",
        note="rounding",
        member_id=Alex.id,
        created_by_telegram_id=42,
    )

    events = expense_repository.list_audit_events(expense.id)
    linked_events = events[-2:]
    assert [event.event_type for event in linked_events] == ["refunded", "corrected"]
    assert linked_events[0].linked_expense_id == refund.id
    assert linked_events[1].linked_expense_id == correction.id


def test_override_exchange_rate_updates_base_splits_and_audit(expense_repository, trip_repository, member_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("JPY", "SGD", "2026-05-20"): "0.0089"})
    money = parse_money("1930", "JPY")
    base, rate = convert_money(money, trip.base_currency, "2026-05-20", provider)
    expense = expense_repository.create_expense(
        trip_id=trip.id,
        description="ramen",
        category="Food",
        expense_date="2026-05-20",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[Alex.id, Sam.id],
        created_by_telegram_id=42,
    )
    manual_base, manual_rate = convert_with_manual_rate(money, "SGD", Decimal("0.008912"), "2026-05-20")

    updated = expense_repository.override_exchange_rate(
        expense.id,
        base_amount_minor=manual_base.amount_minor,
        exchange_rate=manual_rate,
        overridden_by_telegram_id=99,
        actor_display_name="Friend",
    )

    assert updated.original_amount_minor == expense.original_amount_minor
    assert updated.original_currency == "JPY"
    assert updated.base_amount_minor == 1720
    assert updated.exchange_rate_provider == "manual-rate"
    assert sum(split.amount_minor for split in updated.splits) == 1720
    override = expense_repository.list_audit_events(expense.id)[-1]
    assert override.event_type == "rate_overridden"
    assert "fixed" in override.old_value
    assert "manual-rate" in override.new_value

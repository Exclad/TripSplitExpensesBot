from __future__ import annotations

from tripsplitexpenses.balances import calculate_trip_balance
from tripsplitexpenses.exchange import FixedExchangeRateProvider, convert_money
from tripsplitexpenses.money import parse_money


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    alex = member_repository.add_manual_member(trip.id, "Alex", 42)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 42)
    Alex = member_repository.add_manual_member(trip.id, "Taylor", 42)
    return trip, alex, Sam, Alex


def _rate(currency: str = "SGD", base: str = "SGD", date: str = "2026-05-21"):
    return FixedExchangeRateProvider({}).get_rate(currency, base, date)


def test_balance_tracks_paid_consumed_net_and_minimized_settlement(expense_repository, trip_repository, member_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    money = parse_money("90.00", "SGD")
    base, rate = convert_money(money, "SGD", "2026-05-21", FixedExchangeRateProvider({}))
    original = expense_repository.create_expense(
        trip_id=trip.id,
        description="hotel",
        category="Stay",
        expense_date="2026-05-21",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_member_id=Alex.id,
        split_member_ids=[alex.id, Sam.id, Alex.id],
        created_by_telegram_id=42,
    )
    expense_repository.create_refund(
        original_expense_id=original.id,
        recipient_member_id=Sam.id,
        amount_minor=600,
        currency="SGD",
        base_amount_minor=600,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-22",
        created_by_telegram_id=42,
    )
    expense_repository.create_correction(
        original_expense_id=original.id,
        amount_minor=300,
        currency="SGD",
        base_amount_minor=300,
        base_currency="SGD",
        exchange_rate=rate,
        expense_date="2026-05-22",
        note="extra tax",
        member_id=alex.id,
        created_by_telegram_id=42,
    )

    summary = calculate_trip_balance(
        members=member_repository.list_members(trip.id),
        expenses=expense_repository.list_expenses(trip.id),
        base_currency=trip.base_currency,
    )

    by_name = {balance.member_name: balance for balance in summary.balances}
    assert summary.total_spent_minor == 8700
    assert by_name["Alex"].paid_minor == 300
    assert by_name["Alex"].consumed_minor == 3300
    assert by_name["Alex"].net_minor == -3000
    assert by_name["Sam"].paid_minor == -600
    assert by_name["Sam"].consumed_minor == 2400
    assert by_name["Sam"].net_minor == -3000
    assert by_name["Taylor"].paid_minor == 9000
    assert by_name["Taylor"].consumed_minor == 3000
    assert by_name["Taylor"].net_minor == 6000
    assert [(transfer.from_name, transfer.to_name, transfer.amount_minor) for transfer in summary.transfers] == [
        ("Alex", "Taylor", 3000),
        ("Sam", "Taylor", 3000),
    ]


def test_foreign_currency_multiple_payers_allocate_base_paid_amounts(expense_repository, trip_repository, member_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    provider = FixedExchangeRateProvider({("JPY", "SGD", "2026-05-21"): "0.0089"})
    money = parse_money("1001", "JPY")
    base, rate = convert_money(money, "SGD", "2026-05-21", provider)
    expense_repository.create_expense(
        trip_id=trip.id,
        description="tickets",
        category="Transit",
        expense_date="2026-05-21",
        split_method="equal",
        original_amount_minor=money.amount_minor,
        original_currency=money.currency,
        base_amount_minor=base.amount_minor,
        base_currency=base.currency,
        exchange_rate=rate,
        payer_shares={alex.id: 50000, Sam.id: 50100},
        split_member_ids=[alex.id, Sam.id, Alex.id],
        created_by_telegram_id=42,
    )

    summary = calculate_trip_balance(
        members=member_repository.list_members(trip.id),
        expenses=expense_repository.list_expenses(trip.id),
        base_currency=trip.base_currency,
    )

    by_name = {balance.member_name: balance for balance in summary.balances}
    assert summary.total_spent_minor == 891
    assert by_name["Alex"].paid_minor + by_name["Sam"].paid_minor == 891
    assert by_name["Alex"].paid_minor == 445
    assert by_name["Sam"].paid_minor == 446
    assert by_name["Taylor"].paid_minor == 0
    assert sum(balance.net_minor for balance in summary.balances) == 0


def test_exact_one_cent_balance_remains_visible_and_ordering_is_stable(expense_repository, trip_repository, member_repository):
    trip, alex, Sam, Alex = _trip_with_members(trip_repository, member_repository)
    rate = _rate()
    expense_repository.create_expense(
        trip_id=trip.id,
        description="snack",
        category="Food",
        expense_date="2026-05-21",
        split_method="exact",
        original_amount_minor=1,
        original_currency="SGD",
        base_amount_minor=1,
        base_currency="SGD",
        exchange_rate=rate,
        payer_member_id=alex.id,
        exact_shares={Alex.id: 1},
        created_by_telegram_id=42,
    )
    expense_repository.create_expense(
        trip_id=trip.id,
        description="taxi",
        category="Transit",
        expense_date="2026-05-21",
        split_method="exact",
        original_amount_minor=200,
        original_currency="SGD",
        base_amount_minor=200,
        base_currency="SGD",
        exchange_rate=rate,
        payer_member_id=alex.id,
        exact_shares={alex.id: 100, Sam.id: 100},
        created_by_telegram_id=42,
    )

    summary = calculate_trip_balance(
        members=member_repository.list_members(trip.id),
        expenses=expense_repository.list_expenses(trip.id),
        base_currency=trip.base_currency,
    )

    by_name = {balance.member_name: balance for balance in summary.balances}
    assert by_name["Taylor"].net_minor == -1
    assert [(transfer.from_name, transfer.to_name, transfer.amount_minor) for transfer in summary.transfers] == [
        ("Sam", "Alex", 100),
        ("Taylor", "Alex", 1),
    ]

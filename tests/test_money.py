from __future__ import annotations

import pytest

from tripsplitexpenses.money import (
    MoneyError,
    allocate_equal,
    allocate_proportional,
    auto_adjust_rounding,
    format_money,
    parse_money,
    validate_exact_split,
)


def test_parse_money_preserves_cents_and_formats():
    money = parse_money("20.16", "sgd")

    assert money.amount_minor == 2016
    assert money.currency == "SGD"
    assert format_money(money) == "SGD 20.16"


def test_parse_money_rejects_invalid_amount():
    with pytest.raises(MoneyError, match="valid amount"):
        parse_money("abc", "SGD")


def test_equal_split_allocates_every_cent():
    shares = allocate_equal(1000, ["a", "b", "c"])

    assert shares == {"a": 334, "b": 333, "c": 333}
    assert sum(shares.values()) == 1000


def test_exact_split_validation_reports_expected_entered_and_difference():
    with pytest.raises(MoneyError, match="Expected 1000 cents, entered 999 cents, difference 1 cents"):
        validate_exact_split(1000, {"a": 500, "b": 499})


def test_auto_adjust_only_rounding_sized_difference():
    assert auto_adjust_rounding(1000, {"a": 500, "b": 499}) == {"a": 500, "b": 500}
    assert auto_adjust_rounding(1000, {"a": 500, "b": 490}) is None


def test_allocate_proportional_distributes_remainder_deterministically():
    shares = allocate_proportional(101, {"b": 50, "a": 50})

    assert shares == {"b": 50, "a": 51}
    assert sum(shares.values()) == 101

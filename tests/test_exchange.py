from __future__ import annotations

from decimal import Decimal

from tripsplitexpenses.exchange import ExchangeRateProvider, FixedExchangeRateProvider, convert_money, convert_with_exact_base, convert_with_manual_rate
from tripsplitexpenses.money import Money, parse_money


def test_same_currency_conversion_uses_identity_rate():
    base, rate = convert_money(parse_money("25.00", "SGD"), "SGD", "2026-05-20", ExchangeRateProvider())

    assert base.amount_minor == 2500
    assert base.currency == "SGD"
    assert rate.rate == Decimal("1")
    assert rate.provider == "identity"


def test_fixed_foreign_currency_conversion_stores_rate_metadata():
    provider = FixedExchangeRateProvider({("JPY", "SGD", "2026-05-20"): "0.0089"})

    base, rate = convert_money(parse_money("1930", "JPY"), "SGD", "2026-05-20", provider)

    assert base.amount_minor == 1718
    assert base.currency == "SGD"
    assert rate.from_currency == "JPY"
    assert rate.to_currency == "SGD"
    assert rate.date == "2026-05-20"
    assert rate.provider == "fixed"


def test_manual_rate_conversion_returns_exact_base_minor_units():
    base, rate = convert_with_manual_rate(parse_money("1930", "JPY"), "SGD", Decimal("0.008912"), "2026-05-20")

    assert base.amount_minor == 1720
    assert base.currency == "SGD"
    assert rate.rate == Decimal("0.008912")
    assert rate.provider == "manual-rate"


def test_exact_base_equivalent_derives_rate_and_preserves_base_amount():
    base, rate = convert_with_exact_base(parse_money("1930", "JPY"), Money(1720, "SGD"), "2026-05-20")

    assert base.amount_minor == 1720
    assert rate.rate == Decimal("0.0089119171")
    assert rate.provider == "manual-equivalent"

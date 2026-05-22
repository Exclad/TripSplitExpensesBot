from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from tripsplitexpenses.money import Money, normalize_currency


@dataclass(frozen=True)
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    date: str
    provider: str


class ExchangeRateProvider:
    def get_rate(self, from_currency: str, to_currency: str, date: str) -> ExchangeRate:
        from_code = normalize_currency(from_currency)
        to_code = normalize_currency(to_currency)
        if from_code == to_code:
            return ExchangeRate(from_code, to_code, Decimal("1"), date, "identity")
        raise LookupError(f"No exchange rate configured for {from_code}->{to_code} on {date}.")


class FixedExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, rates: dict[tuple[str, str, str], Decimal | str]) -> None:
        self.rates = {(a.upper(), b.upper(), d): Decimal(str(rate)) for (a, b, d), rate in rates.items()}

    def get_rate(self, from_currency: str, to_currency: str, date: str) -> ExchangeRate:
        from_code = normalize_currency(from_currency)
        to_code = normalize_currency(to_currency)
        if from_code == to_code:
            return ExchangeRate(from_code, to_code, Decimal("1"), date, "identity")
        rate = self.rates[(from_code, to_code, date)]
        return ExchangeRate(from_code, to_code, rate, date, "fixed")


def convert_money(money: Money, to_currency: str, date: str, provider: ExchangeRateProvider) -> tuple[Money, ExchangeRate]:
    rate = provider.get_rate(money.currency, to_currency, date)
    amount_minor = int((Decimal(money.amount_minor) * rate.rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Money(amount_minor=amount_minor, currency=rate.to_currency), rate


def convert_with_manual_rate(money: Money, to_currency: str, rate_value: Decimal | str, date: str) -> tuple[Money, ExchangeRate]:
    to_code = normalize_currency(to_currency)
    rate = Decimal(str(rate_value))
    if rate <= 0:
        raise ValueError("Enter a rate greater than zero.")
    amount_minor = int((Decimal(money.amount_minor) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Money(amount_minor=amount_minor, currency=to_code), ExchangeRate(
        from_currency=money.currency,
        to_currency=to_code,
        rate=rate,
        date=date,
        provider="manual-rate",
    )


def convert_with_exact_base(money: Money, base: Money, date: str) -> tuple[Money, ExchangeRate]:
    if money.amount_minor == 0:
        raise ValueError("Cannot derive a rate from a zero amount.")
    rate = (Decimal(base.amount_minor) / Decimal(money.amount_minor)).quantize(Decimal("0.0000000001"))
    return base, ExchangeRate(
        from_currency=money.currency,
        to_currency=base.currency,
        rate=rate,
        date=date,
        provider="manual-equivalent",
    )

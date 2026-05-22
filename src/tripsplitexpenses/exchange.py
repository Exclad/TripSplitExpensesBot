from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from tripsplitexpenses.money import Money, normalize_currency


@dataclass(frozen=True)
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    date: str
    provider: str


class ExchangeRateProvider:
    def __init__(self, timeout_seconds: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self._cache: dict[tuple[str, str, str], ExchangeRate] = {}

    def get_rate(self, from_currency: str, to_currency: str, date: str) -> ExchangeRate:
        from_code = normalize_currency(from_currency)
        to_code = normalize_currency(to_currency)
        if from_code == to_code:
            return ExchangeRate(from_code, to_code, Decimal("1"), date, "identity")
        cache_key = (from_code, to_code, date)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._get_remote_rate(from_code, to_code, date)
        return self._cache[cache_key]

    def _get_remote_rate(self, from_code: str, to_code: str, date: str) -> ExchangeRate:
        errors: list[str] = []
        for rate_date, url in [
            (date, f"https://cdn.jsdelivr.net/gh/fawazahmed0/currency-api@1/{date}/currencies/{from_code.lower()}/{to_code.lower()}.json"),
            ("latest", f"https://cdn.jsdelivr.net/gh/fawazahmed0/currency-api@1/latest/currencies/{from_code.lower()}/{to_code.lower()}.json"),
        ]:
            try:
                with urlopen(url, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                rate = Decimal(str(payload[to_code.lower()]))
                provider_date = str(payload.get("date") or rate_date)
                return ExchangeRate(from_code, to_code, rate, provider_date, "currency-api")
            except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, InvalidOperation) as exc:
                errors.append(str(exc))

        try:
            with urlopen(f"https://open.er-api.com/v6/latest/{from_code}", timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rate = Decimal(str(payload["rates"][to_code]))
            provider_date = str(payload.get("time_last_update_utc") or "latest")
            return ExchangeRate(from_code, to_code, rate, provider_date, "open.er-api")
        except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError, InvalidOperation) as exc:
            errors.append(str(exc))
        raise LookupError(f"No exchange rate available for {from_code}->{to_code} on {date}.")


class FixedExchangeRateProvider(ExchangeRateProvider):
    def __init__(self, rates: dict[tuple[str, str, str], Decimal | str]) -> None:
        super().__init__()
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

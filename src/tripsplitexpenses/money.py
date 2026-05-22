from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class MoneyError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    amount_minor: int
    currency: str

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_minor) / Decimal(100)


def normalize_currency(currency: str) -> str:
    code = currency.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise MoneyError("Use a 3-letter currency code like SGD or JPY.")
    return code


def parse_money(value: str | int | Decimal, currency: str) -> Money:
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise MoneyError("Enter a valid amount, like 25 or 25.50.") from exc
    if amount <= 0:
        raise MoneyError("Amount must be more than 0.")
    minor = int((amount * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Money(amount_minor=minor, currency=normalize_currency(currency))


def format_money(money: Money) -> str:
    if money.currency == "JPY" and money.amount_minor % 100 == 0:
        return f"{money.currency} {money.amount_minor // 100:,}"
    return f"{money.currency} {money.amount:,.2f}"


def allocate_equal(total_minor: int, member_ids: list[str]) -> dict[str, int]:
    if not member_ids:
        raise MoneyError("Add at least one member before saving an expense.")
    share, remainder = divmod(total_minor, len(member_ids))
    return {member_id: share + (1 if index < remainder else 0) for index, member_id in enumerate(member_ids)}


def allocate_proportional(total_minor: int, weights: dict[str, int]) -> dict[str, int]:
    if not weights:
        raise MoneyError("Choose at least one person.")
    if any(weight < 0 for weight in weights.values()):
        raise MoneyError("Weights must not be negative.")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise MoneyError("Choose at least one item participant.")

    sign = -1 if total_minor < 0 else 1
    remaining_total = abs(total_minor)
    base = {
        member_id: (remaining_total * weight) // total_weight
        for member_id, weight in weights.items()
    }
    remainder = remaining_total - sum(base.values())
    ordered = sorted(weights, key=lambda member_id: (-weights[member_id], member_id))
    for member_id in ordered[:remainder]:
        base[member_id] += 1
    return {member_id: amount * sign for member_id, amount in base.items()}


def split_difference(expected_minor: int, shares: dict[str, int]) -> int:
    return expected_minor - sum(shares.values())


def validate_exact_split(expected_minor: int, shares: dict[str, int]) -> None:
    difference = split_difference(expected_minor, shares)
    if difference:
        entered = sum(shares.values())
        raise MoneyError(
            f"Split total does not match. Expected {expected_minor} cents, entered {entered} cents, difference {difference} cents."
        )


def auto_adjust_rounding(expected_minor: int, shares: dict[str, int]) -> dict[str, int] | None:
    difference = split_difference(expected_minor, shares)
    if abs(difference) != 1 or not shares:
        return None
    adjusted = dict(shares)
    last_key = list(adjusted)[-1]
    adjusted[last_key] += difference
    return adjusted

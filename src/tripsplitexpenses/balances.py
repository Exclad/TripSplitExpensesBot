from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tripsplitexpenses.money import allocate_proportional
from tripsplitexpenses.repositories.expenses import Expense
from tripsplitexpenses.repositories.members import Member


@dataclass(frozen=True)
class MemberBalance:
    member_id: str
    member_name: str
    paid_minor: int
    consumed_minor: int
    currency: str

    @property
    def net_minor(self) -> int:
        return self.paid_minor - self.consumed_minor

    @property
    def owes_minor(self) -> int:
        return abs(self.net_minor) if self.net_minor < 0 else 0

    @property
    def is_owed_minor(self) -> int:
        return self.net_minor if self.net_minor > 0 else 0

    @property
    def is_settled(self) -> bool:
        return self.net_minor == 0


@dataclass(frozen=True)
class SettlementTransfer:
    from_member_id: str
    from_name: str
    to_member_id: str
    to_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class CategoryBalance:
    category: str
    total_minor: int
    currency: str


@dataclass(frozen=True)
class PersonAuditRow:
    expense: Expense
    paid_minor: int
    consumed_minor: int

    @property
    def net_minor(self) -> int:
        return self.paid_minor - self.consumed_minor


@dataclass(frozen=True)
class TripBalanceSummary:
    total_spent_minor: int
    base_currency: str
    balances: list[MemberBalance]
    transfers: list[SettlementTransfer]

    @property
    def settled_members(self) -> list[MemberBalance]:
        return [balance for balance in self.balances if balance.is_settled]


def calculate_trip_balance(
    *,
    members: Iterable[Member],
    expenses: Iterable[Expense],
    base_currency: str,
) -> TripBalanceSummary:
    member_list = sorted(members, key=lambda member: (member.display_name.lower(), member.id))
    paid = {member.id: 0 for member in member_list}
    consumed = {member.id: 0 for member in member_list}
    total_spent = 0

    for expense in expenses:
        total_spent += expense.base_amount_minor
        for member_id, amount_minor in base_payer_amounts(expense).items():
            paid[member_id] = paid.get(member_id, 0) + amount_minor
        for split in expense.splits:
            consumed[split.member_id] = consumed.get(split.member_id, 0) + split.amount_minor

    balances = [
        MemberBalance(
            member_id=member.id,
            member_name=member.display_name,
            paid_minor=paid.get(member.id, 0),
            consumed_minor=consumed.get(member.id, 0),
            currency=base_currency.upper(),
        )
        for member in member_list
    ]
    return TripBalanceSummary(
        total_spent_minor=total_spent,
        base_currency=base_currency.upper(),
        balances=balances,
        transfers=_settlement_transfers(balances, base_currency.upper()),
    )


def category_breakdown(expenses: Iterable[Expense], base_currency: str) -> list[CategoryBalance]:
    totals: dict[str, int] = {}
    for expense in expenses:
        totals[expense.category] = totals.get(expense.category, 0) + expense.base_amount_minor
    return [
        CategoryBalance(category=category, total_minor=total, currency=base_currency.upper())
        for category, total in sorted(totals.items(), key=lambda item: (-abs(item[1]), item[0].lower()))
    ]


def person_audit_rows(member_id: str, expenses: Iterable[Expense]) -> list[PersonAuditRow]:
    rows: list[PersonAuditRow] = []
    for expense in expenses:
        paid_minor = base_payer_amounts(expense).get(member_id, 0)
        consumed_minor = sum(split.amount_minor for split in expense.splits if split.member_id == member_id)
        if paid_minor or consumed_minor:
            rows.append(PersonAuditRow(expense=expense, paid_minor=paid_minor, consumed_minor=consumed_minor))
    return rows


def base_payer_amounts(expense: Expense) -> dict[str, int]:
    if not expense.payers:
        return {}
    if expense.original_currency == expense.base_currency:
        return {payer.member_id: payer.amount_minor for payer in expense.payers}

    weights = {payer.member_id: abs(payer.amount_minor) for payer in expense.payers}
    return allocate_proportional(expense.base_amount_minor, weights)


def _settlement_transfers(balances: list[MemberBalance], currency: str) -> list[SettlementTransfer]:
    creditors = [
        [balance.member_id, balance.member_name, balance.net_minor]
        for balance in balances
        if balance.net_minor > 0
    ]
    debtors = [
        [balance.member_id, balance.member_name, -balance.net_minor]
        for balance in balances
        if balance.net_minor < 0
    ]
    creditors.sort(key=lambda row: (-int(row[2]), str(row[1]).lower(), str(row[0])))
    debtors.sort(key=lambda row: (-int(row[2]), str(row[1]).lower(), str(row[0])))

    transfers: list[SettlementTransfer] = []
    creditor_index = 0
    debtor_index = 0
    while creditor_index < len(creditors) and debtor_index < len(debtors):
        debtor = debtors[debtor_index]
        creditor = creditors[creditor_index]
        amount = min(int(debtor[2]), int(creditor[2]))
        if amount:
            transfers.append(
                SettlementTransfer(
                    from_member_id=str(debtor[0]),
                    from_name=str(debtor[1]),
                    to_member_id=str(creditor[0]),
                    to_name=str(creditor[1]),
                    amount_minor=amount,
                    currency=currency,
                )
            )
        debtor[2] = int(debtor[2]) - amount
        creditor[2] = int(creditor[2]) - amount
        if int(debtor[2]) == 0:
            debtor_index += 1
        if int(creditor[2]) == 0:
            creditor_index += 1
    return transfers

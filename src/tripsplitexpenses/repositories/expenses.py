from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
from decimal import Decimal

from tripsplitexpenses.categories import normalize_category
from tripsplitexpenses.exchange import ExchangeRate
from tripsplitexpenses.money import MoneyError, allocate_equal, allocate_proportional, validate_exact_split


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ExpenseSplit:
    member_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class ExpensePayer:
    member_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class ExpenseLineItemShare:
    member_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True)
class ExpenseLineItem:
    id: str
    name: str
    original_amount_minor: int
    base_amount_minor: int
    sort_order: int
    shares: list[ExpenseLineItemShare]


@dataclass(frozen=True)
class ExpenseSharedCharge:
    id: str
    name: str
    original_amount_minor: int
    base_amount_minor: int
    allocation_method: str


@dataclass(frozen=True)
class Expense:
    id: str
    trip_id: str
    description: str
    category: str
    expense_date: str
    split_method: str
    original_amount_minor: int
    original_currency: str
    base_amount_minor: int
    base_currency: str
    exchange_rate: Decimal
    exchange_rate_date: str
    exchange_rate_provider: str
    created_at: str
    updated_at: str
    created_by_telegram_id: int
    payers: list[ExpensePayer]
    splits: list[ExpenseSplit]
    entry_type: str = "expense"
    linked_expense_id: str | None = None
    note: str | None = None
    line_items: list[ExpenseLineItem] = field(default_factory=list)
    shared_charges: list[ExpenseSharedCharge] = field(default_factory=list)


@dataclass(frozen=True)
class ExpenseAuditEvent:
    id: str
    expense_id: str
    event_type: str
    linked_expense_id: str | None
    actor_telegram_id: int | None
    actor_display_name: str | None
    field_name: str | None
    old_value: str | None
    new_value: str | None
    summary: str | None
    created_at: str


class ExpenseRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_expense(
        self,
        *,
        trip_id: str,
        description: str,
        category: str,
        expense_date: str,
        split_method: str,
        original_amount_minor: int,
        original_currency: str,
        base_amount_minor: int,
        base_currency: str,
        exchange_rate: ExchangeRate,
        payer_member_id: str | None = None,
        payer_shares: dict[str, int] | None = None,
        split_member_ids: list[str] | None = None,
        exact_shares: dict[str, int] | None = None,
        itemized_lines: list[dict] | None = None,
        shared_charges: list[dict] | None = None,
        entry_type: str = "expense",
        linked_expense_id: str | None = None,
        note: str | None = None,
        custom_categories: list[str] | None = None,
        created_by_telegram_id: int,
        actor_display_name: str | None = None,
    ) -> Expense:
        if entry_type not in {"expense", "refund", "correction"}:
            raise ValueError("Choose expense, refund, or correction.")
        if entry_type in {"refund", "correction"} and not linked_expense_id:
            raise MoneyError("Choose the original expense.")
        if split_method not in {"equal", "exact", "itemized"}:
            raise ValueError("Choose equal, exact, or itemized split.")
        category = normalize_category(category, custom_categories or ())
        if payer_shares is None:
            if payer_member_id is None:
                raise MoneyError("Choose who paid.")
            payer_shares = {payer_member_id: original_amount_minor}
        self._validate_payers(original_amount_minor, payer_shares)

        itemized_rows: list[dict] = []
        shared_charge_rows: list[dict] = []
        if split_method == "equal":
            if not split_member_ids:
                raise MoneyError("Add at least one member before saving an expense.")
            shares = allocate_equal(base_amount_minor, split_member_ids)
        elif split_method == "exact":
            if not exact_shares:
                raise MoneyError("Enter exact amounts for the selected members.")
            validate_exact_split(base_amount_minor, exact_shares)
            shares = dict(exact_shares)
        else:
            shares, itemized_rows, shared_charge_rows = self._build_itemized_details(
                base_amount_minor=base_amount_minor,
                base_currency=base_currency.upper(),
                itemized_lines=itemized_lines or [],
                shared_charges=shared_charges or [],
            )

        timestamp = _now()
        expense_id = str(uuid.uuid4())
        self.connection.execute(
            """
            INSERT INTO expenses (
                id, trip_id, description, category, expense_date, split_method,
                entry_type, linked_expense_id, note,
                original_amount_minor, original_currency, base_amount_minor, base_currency,
                exchange_rate, exchange_rate_date, exchange_rate_provider,
                created_at, updated_at, created_by_telegram_id, deleted_at, deleted_by_telegram_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense_id,
                trip_id,
                description.strip(),
                category,
                expense_date,
                split_method,
                entry_type,
                linked_expense_id,
                note,
                original_amount_minor,
                original_currency.upper(),
                base_amount_minor,
                base_currency.upper(),
                str(exchange_rate.rate),
                exchange_rate.date,
                exchange_rate.provider,
                timestamp,
                timestamp,
                created_by_telegram_id,
                None,
                None,
            ),
        )
        for member_id, amount_minor in payer_shares.items():
            self.connection.execute(
                """
                INSERT INTO expense_payers (id, expense_id, member_id, amount_minor, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), expense_id, member_id, amount_minor, original_currency.upper(), timestamp),
            )
        for member_id, amount_minor in shares.items():
            self.connection.execute(
                """
                INSERT INTO expense_splits (id, expense_id, member_id, amount_minor, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), expense_id, member_id, amount_minor, base_currency.upper(), timestamp),
            )
        for line in itemized_rows:
            line_id = str(uuid.uuid4())
            self.connection.execute(
                """
                INSERT INTO expense_line_items (
                    id, expense_id, name, original_amount_minor, base_amount_minor, sort_order, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    line_id,
                    expense_id,
                    line["name"],
                    line.get("original_amount_minor", line["base_amount_minor"]),
                    line["base_amount_minor"],
                    line["sort_order"],
                    timestamp,
                ),
            )
            for member_id, amount_minor in line["shares"].items():
                self.connection.execute(
                    """
                    INSERT INTO expense_line_item_shares (
                        id, line_item_id, member_id, amount_minor, currency, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), line_id, member_id, amount_minor, base_currency.upper(), timestamp),
                )
        for charge in shared_charge_rows:
            self.connection.execute(
                """
                INSERT INTO expense_shared_charges (
                    id, expense_id, name, original_amount_minor, base_amount_minor, allocation_method, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    expense_id,
                    charge["name"],
                    charge.get("original_amount_minor", charge["base_amount_minor"]),
                    charge["base_amount_minor"],
                    charge.get("allocation_method", "proportional"),
                    timestamp,
                ),
            )
        self._insert_audit_event(
            expense_id=expense_id,
            event_type="created",
            actor_telegram_id=created_by_telegram_id,
            actor_display_name=actor_display_name,
            linked_expense_id=linked_expense_id,
            summary=f"{entry_type.capitalize()} created.",
            timestamp=timestamp,
        )
        self.connection.commit()
        expense = self.get_expense(expense_id)
        if expense is None:
            raise RuntimeError("Expense was saved but could not be read back.")
        return expense

    def create_refund(
        self,
        *,
        original_expense_id: str,
        recipient_member_id: str,
        amount_minor: int,
        currency: str,
        base_amount_minor: int,
        base_currency: str,
        exchange_rate: ExchangeRate,
        expense_date: str,
        created_by_telegram_id: int,
        actor_display_name: str | None = None,
    ) -> Expense:
        original = self.get_expense(original_expense_id)
        if original is None:
            raise ValueError("Expense not found.")
        refund = self.create_expense(
            trip_id=original.trip_id,
            description=f"Refund: {original.description}",
            category=original.category,
            expense_date=expense_date,
            split_method="exact",
            original_amount_minor=-abs(amount_minor),
            original_currency=currency,
            base_amount_minor=-abs(base_amount_minor),
            base_currency=base_currency,
            exchange_rate=exchange_rate,
            payer_shares={recipient_member_id: -abs(amount_minor)},
            exact_shares={recipient_member_id: -abs(base_amount_minor)},
            entry_type="refund",
            linked_expense_id=original_expense_id,
            note="Refund",
            custom_categories=[original.category],
            created_by_telegram_id=created_by_telegram_id,
            actor_display_name=actor_display_name,
        )
        self._insert_audit_event(
            expense_id=original_expense_id,
            event_type="refunded",
            actor_telegram_id=created_by_telegram_id,
            actor_display_name=actor_display_name,
            linked_expense_id=refund.id,
            summary=f"Refund recorded: {refund.description}.",
        )
        self.connection.commit()
        return refund

    def create_correction(
        self,
        *,
        original_expense_id: str,
        amount_minor: int,
        currency: str,
        base_amount_minor: int,
        base_currency: str,
        exchange_rate: ExchangeRate,
        expense_date: str,
        note: str,
        member_id: str,
        created_by_telegram_id: int,
        actor_display_name: str | None = None,
    ) -> Expense:
        original = self.get_expense(original_expense_id)
        if original is None:
            raise ValueError("Expense not found.")
        correction = self.create_expense(
            trip_id=original.trip_id,
            description=f"Correction: {original.description}",
            category=original.category,
            expense_date=expense_date,
            split_method="exact",
            original_amount_minor=amount_minor,
            original_currency=currency,
            base_amount_minor=base_amount_minor,
            base_currency=base_currency,
            exchange_rate=exchange_rate,
            payer_shares={member_id: amount_minor},
            exact_shares={member_id: base_amount_minor},
            entry_type="correction",
            linked_expense_id=original_expense_id,
            note=note,
            custom_categories=[original.category],
            created_by_telegram_id=created_by_telegram_id,
            actor_display_name=actor_display_name,
        )
        self._insert_audit_event(
            expense_id=original_expense_id,
            event_type="corrected",
            actor_telegram_id=created_by_telegram_id,
            actor_display_name=actor_display_name,
            linked_expense_id=correction.id,
            summary=f"Correction recorded: {note}.",
        )
        self.connection.commit()
        return correction

    def delete_expense(self, expense_id: str, deleted_by_telegram_id: int, actor_display_name: str | None = None) -> None:
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE expenses
            SET deleted_at = ?, deleted_by_telegram_id = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (timestamp, deleted_by_telegram_id, timestamp, expense_id),
        )
        self._insert_audit_event(
            expense_id=expense_id,
            event_type="deleted",
            actor_telegram_id=deleted_by_telegram_id,
            actor_display_name=actor_display_name,
            summary="Expense deleted.",
            timestamp=timestamp,
        )
        self.connection.commit()

    def update_expense(
        self,
        expense_id: str,
        *,
        description: str | None = None,
        category: str | None = None,
        expense_date: str | None = None,
        note: str | None = None,
        custom_categories: list[str] | None = None,
        updated_by_telegram_id: int | None = None,
        actor_display_name: str | None = None,
    ) -> Expense:
        existing = self.get_expense(expense_id)
        if existing is None:
            raise ValueError("Expense not found.")
        updates = []
        params: list[object] = []
        audit_changes: list[tuple[str, object | None, object | None]] = []
        if description is not None:
            updates.append("description = ?")
            normalized_description = description.strip()
            params.append(normalized_description)
            audit_changes.append(("description", existing.description, normalized_description))
        if category is not None:
            normalized_category = normalize_category(category, custom_categories or [existing.category])
            updates.append("category = ?")
            params.append(normalized_category)
            audit_changes.append(("category", existing.category, normalized_category))
        if expense_date is not None:
            updates.append("expense_date = ?")
            params.append(expense_date)
            audit_changes.append(("expense_date", existing.expense_date, expense_date))
        if note is not None:
            updates.append("note = ?")
            params.append(note)
            audit_changes.append(("note", existing.note, note))
        if not updates:
            return existing
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(expense_id)
        self.connection.execute(f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?", params)
        for field_name, old_value, new_value in audit_changes:
            if old_value == new_value:
                continue
            self._insert_audit_event(
                expense_id=expense_id,
                event_type="edited",
                actor_telegram_id=updated_by_telegram_id,
                actor_display_name=actor_display_name,
                field_name=field_name,
                old_value="" if old_value is None else str(old_value),
                new_value="" if new_value is None else str(new_value),
                summary=f"Updated {field_name}.",
            )
        self.connection.commit()
        updated = self.get_expense(expense_id)
        if updated is None:
            raise RuntimeError("Expense was updated but could not be read back.")
        return updated

    def get_expense(self, expense_id: str) -> Expense | None:
        row = self.connection.execute("SELECT * FROM expenses WHERE id = ? AND deleted_at IS NULL", (expense_id,)).fetchone()
        if row is None:
            return None
        return self._expense_from_row(row)

    def list_expenses(self, trip_id: str) -> list[Expense]:
        rows = self.connection.execute(
            "SELECT * FROM expenses WHERE trip_id = ? AND deleted_at IS NULL ORDER BY expense_date DESC, created_at DESC",
            (trip_id,),
        ).fetchall()
        return [self._expense_from_row(row) for row in rows]

    def total_spent_minor(self, trip_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(SUM(base_amount_minor), 0) AS total FROM expenses WHERE trip_id = ? AND deleted_at IS NULL",
            (trip_id,),
        ).fetchone()
        return int(row["total"])

    def list_audit_events(self, expense_id: str) -> list[ExpenseAuditEvent]:
        rows = self.connection.execute(
            """
            SELECT * FROM expense_audit_events
            WHERE expense_id = ?
            ORDER BY created_at, rowid
            """,
            (expense_id,),
        ).fetchall()
        return [self._audit_event_from_row(row) for row in rows]

    def override_exchange_rate(
        self,
        expense_id: str,
        *,
        base_amount_minor: int,
        exchange_rate: ExchangeRate,
        overridden_by_telegram_id: int,
        actor_display_name: str | None = None,
    ) -> Expense:
        existing = self.get_expense(expense_id)
        if existing is None:
            raise ValueError("Expense not found.")
        previous = (
            f"{existing.base_currency} {existing.base_amount_minor} at "
            f"{existing.exchange_rate} from {existing.exchange_rate_provider} on {existing.exchange_rate_date}"
        )
        replacement = (
            f"{exchange_rate.to_currency} {base_amount_minor} at "
            f"{exchange_rate.rate} from {exchange_rate.provider} on {exchange_rate.date}"
        )
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE expenses
            SET base_amount_minor = ?,
                base_currency = ?,
                exchange_rate = ?,
                exchange_rate_date = ?,
                exchange_rate_provider = ?,
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (
                base_amount_minor,
                exchange_rate.to_currency,
                str(exchange_rate.rate),
                exchange_rate.date,
                exchange_rate.provider,
                timestamp,
                expense_id,
            ),
        )
        split_weights = {split.member_id: abs(split.amount_minor) for split in existing.splits}
        if existing.split_method == "equal":
            new_splits = allocate_equal(base_amount_minor, [split.member_id for split in existing.splits])
        else:
            new_splits = allocate_proportional(base_amount_minor, split_weights)
        self.connection.execute("DELETE FROM expense_splits WHERE expense_id = ?", (expense_id,))
        for member_id, amount_minor in new_splits.items():
            self.connection.execute(
                """
                INSERT INTO expense_splits (id, expense_id, member_id, amount_minor, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), expense_id, member_id, amount_minor, exchange_rate.to_currency, timestamp),
            )
        self._insert_audit_event(
            expense_id=expense_id,
            event_type="rate_overridden",
            actor_telegram_id=overridden_by_telegram_id,
            actor_display_name=actor_display_name,
            old_value=previous,
            new_value=replacement,
            summary=f"Rate overridden from {previous} to {replacement}.",
            timestamp=timestamp,
        )
        self.connection.commit()
        updated = self.get_expense(expense_id)
        if updated is None:
            raise RuntimeError("Expense was updated but could not be read back.")
        return updated

    def _validate_payers(self, expected_minor: int, payer_shares: dict[str, int]) -> None:
        if not payer_shares:
            raise MoneyError("Choose who paid.")
        total = sum(payer_shares.values())
        if total != expected_minor:
            raise MoneyError(
                f"Payer total does not match. Expected {expected_minor} cents, entered {total} cents, difference {expected_minor - total} cents."
            )

    def _build_itemized_details(
        self,
        *,
        base_amount_minor: int,
        base_currency: str,
        itemized_lines: list[dict],
        shared_charges: list[dict],
    ) -> tuple[dict[str, int], list[dict], list[dict]]:
        if not itemized_lines:
            raise MoneyError("Add at least one line item.")
        final_shares: dict[str, int] = {}
        normalized_lines: list[dict] = []
        line_weights: dict[str, int] = {}
        for index, line in enumerate(itemized_lines):
            participants = list(line.get("member_ids") or [])
            amount_minor = int(line["base_amount_minor"])
            shares = allocate_equal(amount_minor, participants)
            for member_id, amount in shares.items():
                final_shares[member_id] = final_shares.get(member_id, 0) + amount
                line_weights[member_id] = line_weights.get(member_id, 0) + amount
            normalized_lines.append(
                {
                    "name": line["name"].strip(),
                    "base_amount_minor": amount_minor,
                    "original_amount_minor": int(line.get("original_amount_minor", amount_minor)),
                    "sort_order": index,
                    "shares": shares,
                }
            )
        normalized_charges: list[dict] = []
        for charge in shared_charges:
            amount_minor = int(charge["base_amount_minor"])
            charge_shares = allocate_proportional(amount_minor, line_weights)
            for member_id, amount in charge_shares.items():
                final_shares[member_id] = final_shares.get(member_id, 0) + amount
            normalized_charges.append(
                {
                    "name": charge["name"].strip(),
                    "base_amount_minor": amount_minor,
                    "original_amount_minor": int(charge.get("original_amount_minor", amount_minor)),
                    "allocation_method": "proportional",
                }
            )
        validate_exact_split(base_amount_minor, final_shares)
        return final_shares, normalized_lines, normalized_charges

    def _expense_from_row(self, row: sqlite3.Row) -> Expense:
        payers = [
            ExpensePayer(member_id=r["member_id"], amount_minor=r["amount_minor"], currency=r["currency"])
            for r in self.connection.execute("SELECT * FROM expense_payers WHERE expense_id = ?", (row["id"],)).fetchall()
        ]
        splits = [
            ExpenseSplit(member_id=r["member_id"], amount_minor=r["amount_minor"], currency=r["currency"])
            for r in self.connection.execute("SELECT * FROM expense_splits WHERE expense_id = ?", (row["id"],)).fetchall()
        ]
        line_items: list[ExpenseLineItem] = []
        for line in self.connection.execute(
            "SELECT * FROM expense_line_items WHERE expense_id = ? ORDER BY sort_order, created_at",
            (row["id"],),
        ).fetchall():
            line_shares = [
                ExpenseLineItemShare(member_id=r["member_id"], amount_minor=r["amount_minor"], currency=r["currency"])
                for r in self.connection.execute("SELECT * FROM expense_line_item_shares WHERE line_item_id = ?", (line["id"],)).fetchall()
            ]
            line_items.append(
                ExpenseLineItem(
                    id=line["id"],
                    name=line["name"],
                    original_amount_minor=line["original_amount_minor"],
                    base_amount_minor=line["base_amount_minor"],
                    sort_order=line["sort_order"],
                    shares=line_shares,
                )
            )
        shared_charges = [
            ExpenseSharedCharge(
                id=r["id"],
                name=r["name"],
                original_amount_minor=r["original_amount_minor"],
                base_amount_minor=r["base_amount_minor"],
                allocation_method=r["allocation_method"],
            )
            for r in self.connection.execute("SELECT * FROM expense_shared_charges WHERE expense_id = ?", (row["id"],)).fetchall()
        ]
        return Expense(
            id=row["id"],
            trip_id=row["trip_id"],
            description=row["description"],
            category=row["category"],
            entry_type=row["entry_type"],
            linked_expense_id=row["linked_expense_id"],
            note=row["note"],
            expense_date=row["expense_date"],
            split_method=row["split_method"],
            original_amount_minor=row["original_amount_minor"],
            original_currency=row["original_currency"],
            base_amount_minor=row["base_amount_minor"],
            base_currency=row["base_currency"],
            exchange_rate=Decimal(row["exchange_rate"]),
            exchange_rate_date=row["exchange_rate_date"],
            exchange_rate_provider=row["exchange_rate_provider"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by_telegram_id=row["created_by_telegram_id"],
            payers=payers,
            splits=splits,
            line_items=line_items,
            shared_charges=shared_charges,
        )

    def _insert_audit_event(
        self,
        *,
        expense_id: str,
        event_type: str,
        actor_telegram_id: int | None,
        actor_display_name: str | None = None,
        linked_expense_id: str | None = None,
        field_name: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        summary: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO expense_audit_events (
                id, expense_id, event_type, linked_expense_id, actor_telegram_id,
                actor_display_name, field_name, old_value, new_value, summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                expense_id,
                event_type,
                linked_expense_id,
                actor_telegram_id,
                actor_display_name,
                field_name,
                old_value,
                new_value,
                summary,
                timestamp or _now(),
            ),
        )

    def _audit_event_from_row(self, row: sqlite3.Row) -> ExpenseAuditEvent:
        return ExpenseAuditEvent(
            id=row["id"],
            expense_id=row["expense_id"],
            event_type=row["event_type"],
            linked_expense_id=row["linked_expense_id"],
            actor_telegram_id=row["actor_telegram_id"],
            actor_display_name=row["actor_display_name"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            summary=row["summary"],
            created_at=row["created_at"],
        )

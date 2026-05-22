from __future__ import annotations

from tripsplitexpenses.balances import CategoryBalance, MemberBalance, PersonAuditRow, TripBalanceSummary
from tripsplitexpenses.money import Money, format_money
from tripsplitexpenses.repositories.expenses import Expense, ExpenseAuditEvent
from tripsplitexpenses.repositories.members import Member


def format_amount_pair(original: Money, base: Money) -> str:
    original_text = format_money(original)
    base_text = format_money(base)
    if original.currency == base.currency and original.amount_minor == base.amount_minor:
        return original_text
    return f"{original_text} (~{base_text})"


def format_payer_summary(names: list[str]) -> str:
    if not names:
        return "unknown"
    if len(names) == 1:
        return names[0]
    return " + ".join(names)


def format_confirmation(draft: dict, members: list[Member]) -> str:
    selected = set(draft.get("split_member_ids", []))
    names = [member.display_name for member in members if member.id in selected]
    people = ", ".join(names) if names else "No members selected"
    amount = format_amount_pair(draft["original_money"], draft["base_money"])
    payer = draft.get("payer_summary") or draft.get("payer_name", "You")
    if draft.get("payer_shares"):
        payer = format_payer_summary([member.display_name for member in members if member.id in draft["payer_shares"]])
    itemized = ""
    if draft.get("itemized_lines"):
        itemized = f"\nItems: {len(draft['itemized_lines'])}"
    return (
        f"Ready to save?\n"
        f"{draft['description']} - {amount}\n"
        f"Category: {draft['category']}\n"
        f"Date: {draft['expense_date']}\n"
        f"Paid by: {payer}\n"
        f"Split: {draft['split_method']} with {people}"
        f"{itemized}"
    )


def format_saved_expense(expense: Expense, payer_name: str, split_count: int) -> str:
    amount = format_amount_pair(
        Money(expense.original_amount_minor, expense.original_currency),
        Money(expense.base_amount_minor, expense.base_currency),
    )
    prefix = {"expense": "Saved", "refund": "Refund", "correction": "Correction"}.get(expense.entry_type, "Saved")
    item_text = f" - {len(expense.line_items)} items" if expense.line_items else ""
    return (
        f"{prefix}: {expense.description} - {amount}\n"
        f"{expense.category} - paid by {payer_name} - split {split_count} ways{item_text}"
    )


def format_exchange_details(expense: Expense) -> str:
    original = format_money(Money(expense.original_amount_minor, expense.original_currency))
    base = format_money(Money(expense.base_amount_minor, expense.base_currency))
    override = "\nManual override: yes" if expense.exchange_rate_provider.startswith("manual") else ""
    return (
        f"Original: {original}\n"
        f"Trip amount: {base}\n"
        f"Type: {expense.entry_type}\n"
        f"Rate: 1 {expense.original_currency} = {expense.exchange_rate} {expense.base_currency}\n"
        f"Rate date: {expense.exchange_rate_date}\n"
        f"Source: {expense.exchange_rate_provider}"
        f"{override}"
    )


def format_expense_history(events: list[ExpenseAuditEvent], actor_names: dict[int, str]) -> str:
    lines = ["History"]
    if not events:
        lines.append("- No history yet.")
        return "\n".join(lines)
    for event in events:
        actor = _format_actor(event, actor_names)
        prefix = f"- {event.created_at}: {actor}"
        if event.event_type == "edited" and event.field_name:
            lines.append(f"{prefix} changed {event.field_name} from {event.old_value or '(blank)'} to {event.new_value or '(blank)'}")
        elif event.event_type == "created":
            lines.append(f"{prefix} created this {event.summary or 'expense.'}")
        elif event.event_type == "deleted":
            lines.append(f"{prefix} deleted this expense")
        elif event.event_type in {"refunded", "corrected", "rate_overridden"}:
            lines.append(f"{prefix} {event.summary or event.event_type.replace('_', ' ')}")
        else:
            lines.append(f"{prefix} {event.summary or event.event_type.replace('_', ' ')}")
    return "\n".join(lines)


def format_balance_summary(summary: TripBalanceSummary) -> str:
    total = format_money(Money(summary.total_spent_minor, summary.base_currency))
    lines = ["Settle up"]
    if summary.transfers:
        lines.extend(
            f"- {transfer.from_name} pays {transfer.to_name} {format_money(Money(transfer.amount_minor, transfer.currency))}"
            for transfer in summary.transfers
        )
    elif summary.total_spent_minor == 0:
        lines.append("No expenses yet.")
    else:
        lines.append("Everyone is settled.")

    lines.append("")
    lines.append(f"Total spent: {total}")
    lines.append("")
    lines.append("By person")
    for balance in summary.balances:
        net = format_money(Money(abs(balance.net_minor), balance.currency))
        if balance.net_minor > 0:
            lines.append(f"- {balance.member_name} should receive {net}")
        elif balance.net_minor < 0:
            lines.append(f"- {balance.member_name} owes {net}")
        else:
            lines.append(f"- {balance.member_name} is settled")
    return "\n".join(lines)


def format_person_breakdown(summary: TripBalanceSummary) -> str:
    lines = ["Person breakdown"]
    for balance in summary.balances:
        lines.append("")
        lines.append(balance.member_name)
        lines.append(f"Paid: {format_money(Money(balance.paid_minor, balance.currency))}")
        lines.append(f"Consumed: {format_money(Money(balance.consumed_minor, balance.currency))}")
        lines.append(f"Owes: {format_money(Money(balance.owes_minor, balance.currency))}")
        lines.append(f"Is owed: {format_money(Money(balance.is_owed_minor, balance.currency))}")
    return "\n".join(lines)


def format_category_breakdown(rows: list[CategoryBalance]) -> str:
    if not rows:
        return "Category breakdown\nNo expenses yet."
    lines = ["Category breakdown"]
    lines.extend(f"- {row.category}: {format_money(Money(row.total_minor, row.currency))}" for row in rows)
    return "\n".join(lines)


def format_expense_list(expenses: list[Expense], name_by_member_id: dict[str, str], *, offset: int, total: int) -> str:
    if total == 0:
        return "Expenses\nNo expenses yet."
    end = offset + len(expenses)
    lines = [f"Expenses {offset + 1}-{end} of {total}"]
    lines.extend(_format_expense_row(expense, name_by_member_id) for expense in expenses)
    return "\n".join(lines)


def format_audit_menu() -> str:
    return "Audit by person"


def format_person_audit(member_name: str, balance: MemberBalance, rows: list[PersonAuditRow], name_by_member_id: dict[str, str]) -> str:
    direction = "owes" if balance.net_minor < 0 else "is owed" if balance.net_minor > 0 else "is settled"
    lines = [
        f"Why {member_name} {direction}",
        f"Paid minus consumed = {format_money(Money(balance.net_minor, balance.currency))}",
        f"Paid: {format_money(Money(balance.paid_minor, balance.currency))}",
        f"Consumed: {format_money(Money(balance.consumed_minor, balance.currency))}",
        f"Net: {format_money(Money(balance.net_minor, balance.currency))}",
        "",
        "Expense rows",
    ]
    if not rows:
        lines.append("No expense rows for this person yet.")
    else:
        for row in rows:
            lines.append(_format_audit_row(row, name_by_member_id))
    lines.append("")
    lines.append("Split cents were assigned consistently so totals match.")
    return "\n".join(lines)


def _format_expense_row(expense: Expense, name_by_member_id: dict[str, str]) -> str:
    amount = format_amount_pair(
        Money(expense.original_amount_minor, expense.original_currency),
        Money(expense.base_amount_minor, expense.base_currency),
    )
    payer_names = [name_by_member_id.get(payer.member_id, "unknown") for payer in expense.payers]
    return (
        f"- {expense.description} - {expense.expense_date} - {expense.category} - {amount} - "
        f"paid by {format_payer_summary(payer_names)} - split {len(expense.splits)} ways"
    )


def _format_audit_row(row: PersonAuditRow, name_by_member_id: dict[str, str]) -> str:
    expense = row.expense
    label = {"expense": "Expense", "refund": "Refund", "correction": "Correction"}.get(expense.entry_type, "Expense")
    base = format_money(Money(expense.base_amount_minor, expense.base_currency))
    row_text = (
        f"- {label}: {_format_expense_row(expense, name_by_member_id)[2:]} "
        f"(paid {format_money(Money(row.paid_minor, expense.base_currency))}, "
        f"consumed {format_money(Money(row.consumed_minor, expense.base_currency))}, "
        f"net {format_money(Money(row.net_minor, expense.base_currency))})"
    )
    if expense.original_currency != expense.base_currency:
        row_text += f" Rate: 1 {expense.original_currency} = {expense.exchange_rate} {expense.base_currency} on {expense.exchange_rate_date}"
    elif expense.entry_type != "expense":
        row_text += f" Base amount: {base}"
    return row_text


def _format_actor(event: ExpenseAuditEvent, actor_names: dict[int, str]) -> str:
    if event.actor_telegram_id is not None and event.actor_telegram_id in actor_names:
        return actor_names[event.actor_telegram_id]
    if event.actor_display_name:
        return event.actor_display_name
    if event.actor_telegram_id is not None:
        return f"Telegram user {event.actor_telegram_id}"
    return "Someone"

from __future__ import annotations

from typing import Any

from tripsplitexpenses.balances import calculate_trip_balance, category_breakdown, person_audit_rows
from tripsplitexpenses.bot.copy import MISSING_TRIP_MESSAGE
from tripsplitexpenses.bot.formatters import (
    format_audit_menu,
    format_balance_summary,
    format_category_breakdown,
    format_expense_list,
    format_person_audit,
    format_person_breakdown,
)
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.repositories.members import Member, MemberRepository
from tripsplitexpenses.repositories.trips import TripRepository

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # pragma: no cover
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class InlineKeyboardButton:  # type: ignore[no-redef]
        text: str
        callback_data: str

    @dataclass(frozen=True)
    class InlineKeyboardMarkup:  # type: ignore[no-redef]
        inline_keyboard: list[list[InlineKeyboardButton]]


def _expense_repository(context: Any) -> ExpenseRepository:
    repository = context.application.bot_data.get("expense_repository")
    if repository is None:
        repository = ExpenseRepository(context.application.bot_data["connection"])
        context.application.bot_data["expense_repository"] = repository
    return repository


def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Person breakdown", callback_data="balance:people"),
                InlineKeyboardButton("Category breakdown", callback_data="balance:categories"),
            ],
            [
                InlineKeyboardButton("Expense list", callback_data="balance:expenses:0"),
                InlineKeyboardButton("Audit", callback_data="balance:audit"),
            ],
        ]
    )


def audit_member_keyboard(members: list[Member]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(member.display_name, callback_data=f"balance:audit-person:{member.id}")] for member in members]
    )


def expense_page_keyboard(offset: int, page_size: int, total: int) -> InlineKeyboardMarkup | None:
    next_offset = offset + page_size
    if next_offset >= total:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("Next", callback_data=f"balance:expenses:{next_offset}")]])


async def balance_command(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    members = member_repository.list_members(trip.id)
    expenses = _expense_repository(context).list_expenses(trip.id)
    summary = calculate_trip_balance(members=members, expenses=expenses, base_currency=trip.base_currency)
    await update.message.reply_text(format_balance_summary(summary), reply_markup=balance_keyboard())


async def balance_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    await query.answer()
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await query.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    members = member_repository.list_members(trip.id)
    expenses = _expense_repository(context).list_expenses(trip.id)
    summary = calculate_trip_balance(members=members, expenses=expenses, base_currency=trip.base_currency)
    name_by_member_id = {member.id: member.display_name for member in members}
    data = query.data or ""

    if data == "balance:people":
        await query.message.reply_text(format_person_breakdown(summary))
        return
    if data == "balance:categories":
        await query.message.reply_text(format_category_breakdown(category_breakdown(expenses, trip.base_currency)))
        return
    if data.startswith("balance:expenses:"):
        offset = _parse_offset(data)
        page_size = 10
        page = expenses[offset : offset + page_size]
        keyboard = expense_page_keyboard(offset, page_size, len(expenses))
        if keyboard is None:
            await query.message.reply_text(format_expense_list(page, name_by_member_id, offset=offset, total=len(expenses)))
        else:
            await query.message.reply_text(format_expense_list(page, name_by_member_id, offset=offset, total=len(expenses)), reply_markup=keyboard)
        return
    if data == "balance:audit":
        await query.message.reply_text(format_audit_menu(), reply_markup=audit_member_keyboard(members))
        return
    if data.startswith("balance:audit-person:"):
        member_id = data.removeprefix("balance:audit-person:")
        member = next((item for item in members if item.id == member_id), None)
        balance = next((item for item in summary.balances if item.member_id == member_id), None)
        if member is None or balance is None:
            await query.message.reply_text("Member not found.")
            return
        await query.message.reply_text(format_person_audit(member.display_name, balance, person_audit_rows(member.id, expenses), name_by_member_id))
        return
    await query.message.reply_text("Balance view not found.")


def _parse_offset(data: str) -> int:
    try:
        return max(0, int(data.rsplit(":", 1)[1]))
    except ValueError:
        return 0

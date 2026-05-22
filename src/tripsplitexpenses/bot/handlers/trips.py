from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tripsplitexpenses.bot.copy import (
    ARCHIVE_CONFIRM_MESSAGE,
    DUPLICATE_TRIP_MESSAGE,
    JOIN_CALLBACK_DATA,
    MISSING_TRIP_MESSAGE,
    NEWTRIP_GUIDE_MESSAGE,
    REOPEN_CONFIRM_MESSAGE,
)
from tripsplitexpenses.repositories.members import MemberRepository
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.repositories.trips import ActiveTripExistsError, TripIsArchivedError, TripNotFoundError, TripRepository
from tripsplitexpenses.money import Money, format_money

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # pragma: no cover - tests use the lightweight fallback.

    @dataclass(frozen=True)
    class InlineKeyboardButton:  # type: ignore[no-redef]
        text: str
        callback_data: str

    @dataclass(frozen=True)
    class InlineKeyboardMarkup:  # type: ignore[no-redef]
        inline_keyboard: list[list[InlineKeyboardButton]]


def parse_newtrip_args(text: str) -> tuple[str | None, str | None]:
    parts = text.split()
    args = parts[1:] if parts and parts[0].startswith("/newtrip") else parts
    if len(args) < 2:
        return None, None

    currency = args[-1].upper()
    name = " ".join(args[:-1]).strip()
    if len(currency) != 3 or not currency.isalpha() or not name:
        return None, None
    return name, currency


async def newtrip(update: Any, context: Any) -> None:
    name, base_currency = parse_newtrip_args(update.message.text or "")
    if not name or not base_currency:
        await update.message.reply_text(NEWTRIP_GUIDE_MESSAGE)
        return

    repository: TripRepository = context.application.bot_data["trip_repository"]
    try:
        trip = repository.create_trip(
            telegram_chat_id=update.effective_chat.id,
            name=name,
            base_currency=base_currency,
            created_by_telegram_id=update.effective_user.id,
        )
    except ActiveTripExistsError:
        await update.message.reply_text(DUPLICATE_TRIP_MESSAGE)
        return

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join this trip", callback_data=JOIN_CALLBACK_DATA)]])
    await update.message.reply_text(
        f"Trip created: {trip.name} ({trip.base_currency}). Tap Join this trip so I know who is coming.",
        reply_markup=keyboard,
    )


async def trip_status(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    expense_repository: ExpenseRepository | None = context.application.bot_data.get("expense_repository")
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    members = member_repository.list_members(trip.id)
    total_minor = expense_repository.total_spent_minor(trip.id) if expense_repository else 0
    member_lines = "\n".join(f"- {member.display_name}" for member in members) or "- No members yet. Tap Join this trip."
    status_line = "Status: Archived - read-only until reopened." if trip.status == "archived" else "Status: Active"
    await update.message.reply_text(
        f"{trip.name}\n"
        f"{status_line}\n"
        f"Base currency: {trip.base_currency}\n"
        f"Total spent: {format_money(Money(total_minor, trip.base_currency))}\n"
        f"Members: {len(members)}\n"
        f"{member_lines}"
    )


def _confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"trip:{action}:confirm"),
                InlineKeyboardButton("Cancel", callback_data=f"trip:{action}:cancel"),
            ]
        ]
    )


async def archive_command(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    await update.message.reply_text(ARCHIVE_CONFIRM_MESSAGE, reply_markup=_confirm_keyboard("archive"))


async def reopen_command(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    if trip.status == "active":
        await update.message.reply_text("This trip is already active.")
        return
    await update.message.reply_text(REOPEN_CONFIRM_MESSAGE, reply_markup=_confirm_keyboard("reopen"))


async def trip_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    data = query.data or ""
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    if data == "trip:archive:cancel" or data == "trip:reopen:cancel":
        await query.answer("Cancelled")
        await query.message.reply_text("Cancelled. Nothing changed.")
        return
    if data == "trip:archive:confirm":
        trip = trip_repository.get_active_trip(update.effective_chat.id)
        if trip is None:
            await query.answer("No active trip")
            await query.message.reply_text(MISSING_TRIP_MESSAGE)
            return
        try:
            trip_repository.archive_trip(trip.id, update.effective_user.id)
        except (TripIsArchivedError, TripNotFoundError) as exc:
            await query.answer("Not archived")
            await query.message.reply_text(str(exc))
            return
        await query.answer("Archived")
        await query.message.reply_text(f"Archived {trip.name}. You can still use /trip and /balance, or /reopen when needed.")
        return
    if data == "trip:reopen:confirm":
        trip = trip_repository.get_readable_trip(update.effective_chat.id)
        if trip is None:
            await query.answer("No trip")
            await query.message.reply_text(MISSING_TRIP_MESSAGE)
            return
        try:
            reopened = trip_repository.reopen_trip(trip.id, update.effective_user.id)
        except ActiveTripExistsError:
            await query.answer("Active trip exists")
            await query.message.reply_text(DUPLICATE_TRIP_MESSAGE)
            return
        await query.answer("Reopened")
        await query.message.reply_text(f"Reopened {reopened.name}. Expense edits are available again.")
        return
    await query.answer("Trip action not found.")

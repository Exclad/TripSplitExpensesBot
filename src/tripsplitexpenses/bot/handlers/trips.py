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
from tripsplitexpenses.bot.menu import active_menu, menu_for_chat, setup_menu
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


def _setup_drafts(context: Any) -> dict[tuple[int, int], dict]:
    return context.application.bot_data.setdefault("trip_setup_drafts", {})


def _draft_key(update: Any) -> tuple[int, int]:
    return (update.effective_chat.id, update.effective_user.id)


def parse_newtrip_args(text: str) -> tuple[str | None, str | None, str | None]:
    parts = text.split()
    args = parts[1:] if parts and parts[0].startswith("/newtrip") else parts
    if len(args) < 2:
        return None, None, None

    base_currency = args[-1].upper()
    default_expense_currency = base_currency
    name_args = args[:-1]
    if len(args) >= 3 and _looks_like_currency(args[-1]) and _looks_like_currency(args[-2]):
        base_currency = args[-2].upper()
        default_expense_currency = args[-1].upper()
        name_args = args[:-2]
    name = " ".join(name_args).strip()
    if not _looks_like_currency(base_currency) or not _looks_like_currency(default_expense_currency) or not name:
        return None, None, None
    return name, base_currency, default_expense_currency


async def newtrip(update: Any, context: Any) -> None:
    name, base_currency, default_expense_currency = parse_newtrip_args(update.message.text or "")
    if not name or not base_currency:
        await start_setup(update, context)
        return

    repository: TripRepository = context.application.bot_data["trip_repository"]
    try:
        trip = repository.create_trip(
            telegram_chat_id=update.effective_chat.id,
            name=name,
            base_currency=base_currency,
            default_expense_currency=default_expense_currency,
            created_by_telegram_id=update.effective_user.id,
        )
    except ActiveTripExistsError:
        await update.message.reply_text(DUPLICATE_TRIP_MESSAGE, reply_markup=active_menu())
        return

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join this trip", callback_data=JOIN_CALLBACK_DATA)]])
    await update.message.reply_text(
        f"Trip created: {trip.name}.\n"
        f"Settlement currency: {trip.base_currency}\n"
        f"Default expense currency: {trip.default_expense_currency}\n"
        "Tap Join this trip so I know who is coming.",
        reply_markup=keyboard,
    )
    await update.message.reply_text("Main buttons are ready.", reply_markup=active_menu())


async def start_setup(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    if trip_repository.get_active_trip(update.effective_chat.id) is not None:
        await update.message.reply_text(DUPLICATE_TRIP_MESSAGE, reply_markup=active_menu())
        return
    _setup_drafts(context)[_draft_key(update)] = {"flow": "setup_name"}
    await update.message.reply_text("What should we call this trip?", reply_markup=setup_menu())


async def setup_message(update: Any, context: Any) -> bool:
    draft = _setup_drafts(context).get(_draft_key(update))
    if draft is None:
        return False
    text = (update.message.text or "").strip()
    if text.lower() == "cancel":
        _setup_drafts(context).pop(_draft_key(update), None)
        await update.message.reply_text("Cancelled. No trip was created.", reply_markup=setup_menu())
        return True
    if draft["flow"] == "setup_name":
        if not text:
            await update.message.reply_text("Send a trip name, like Korea 2026.")
            return True
        draft["name"] = text
        draft["flow"] = "setup_base_currency"
        await update.message.reply_text("What currency should settlements use? Send a 3-letter code like SGD.")
        return True
    if draft["flow"] == "setup_base_currency":
        if not _looks_like_currency(text):
            await update.message.reply_text("Use a 3-letter currency code like SGD.")
            return True
        draft["base_currency"] = text.upper()
        draft["flow"] = "setup_default_currency"
        await update.message.reply_text("What currency will expenses usually be in? Send a 3-letter code like KRW.")
        return True
    if draft["flow"] == "setup_default_currency":
        if not _looks_like_currency(text):
            await update.message.reply_text("Use a 3-letter currency code like KRW.")
            return True
        draft["default_expense_currency"] = text.upper()
        draft["flow"] = "setup_confirm"
        await update.message.reply_text(
            f"Create {draft['name']}?\n"
            f"Settlement currency: {draft['base_currency']}\n"
            f"Default expense currency: {draft['default_expense_currency']}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Create trip", callback_data="trip:setup:confirm"),
                        InlineKeyboardButton("Cancel", callback_data="trip:setup:cancel"),
                    ]
                ]
            ),
        )
        return True
    return True


async def trip_status(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    expense_repository: ExpenseRepository | None = context.application.bot_data.get("expense_repository")
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
        return

    members = member_repository.list_members(trip.id)
    total_minor = expense_repository.total_spent_minor(trip.id) if expense_repository else 0
    member_lines = "\n".join(f"- {member.display_name}" for member in members) or "- No members yet. Tap Join this trip."
    status_line = "Status: Archived - read-only until reopened." if trip.status == "archived" else "Status: Active"
    await update.message.reply_text(
        f"{trip.name}\n"
        f"{status_line}\n"
        f"Settlement currency: {trip.base_currency}\n"
        f"Default expense currency: {trip.default_expense_currency}\n"
        f"Total spent: {format_money(Money(total_minor, trip.base_currency))}\n"
        f"Members: {len(members)}\n"
        f"{member_lines}",
        reply_markup=menu_for_chat(context, update.effective_chat.id),
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
        await update.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    await update.message.reply_text(ARCHIVE_CONFIRM_MESSAGE, reply_markup=_confirm_keyboard("archive"))


async def reopen_command(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    if trip.status == "active":
        await update.message.reply_text("This trip is already active.", reply_markup=active_menu())
        return
    await update.message.reply_text(REOPEN_CONFIRM_MESSAGE, reply_markup=_confirm_keyboard("reopen"))


async def trip_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    data = query.data or ""
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    if data == "trip:setup:cancel":
        _setup_drafts(context).pop(_draft_key(update), None)
        await query.answer("Cancelled")
        await query.message.reply_text("Cancelled. No trip was created.", reply_markup=setup_menu())
        return
    if data == "trip:setup:confirm":
        draft = _setup_drafts(context).get(_draft_key(update))
        if draft is None:
            await query.answer("Setup expired")
            await query.message.reply_text("Start setup again from the menu.", reply_markup=setup_menu())
            return
        try:
            trip = trip_repository.create_trip(
                telegram_chat_id=update.effective_chat.id,
                name=draft["name"],
                base_currency=draft["base_currency"],
                default_expense_currency=draft["default_expense_currency"],
                created_by_telegram_id=update.effective_user.id,
            )
        except ActiveTripExistsError:
            await query.answer("Trip exists")
            await query.message.reply_text(DUPLICATE_TRIP_MESSAGE, reply_markup=active_menu())
            return
        _setup_drafts(context).pop(_draft_key(update), None)
        await query.answer("Trip created")
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join this trip", callback_data=JOIN_CALLBACK_DATA)]])
        await query.message.reply_text(
            f"Trip created: {trip.name}.\n"
            f"Settlement currency: {trip.base_currency}\n"
            f"Default expense currency: {trip.default_expense_currency}\n"
            "Tap Join this trip, then add anyone missing from Members.",
            reply_markup=keyboard,
        )
        await query.message.reply_text("Main buttons are ready.", reply_markup=active_menu())
        return
    if data == "trip:archive:cancel" or data == "trip:reopen:cancel":
        await query.answer("Cancelled")
        await query.message.reply_text("Cancelled. Nothing changed.", reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    if data == "trip:archive:confirm":
        trip = trip_repository.get_active_trip(update.effective_chat.id)
        if trip is None:
            await query.answer("No active trip")
            await query.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
            return
        try:
            trip_repository.archive_trip(trip.id, update.effective_user.id)
        except (TripIsArchivedError, TripNotFoundError) as exc:
            await query.answer("Not archived")
            await query.message.reply_text(str(exc), reply_markup=menu_for_chat(context, update.effective_chat.id))
            return
        await query.answer("Archived")
        await query.message.reply_text(
            f"Archived {trip.name}. Tap Set up trip to start another, or use /reopen to edit this one again.",
            reply_markup=menu_for_chat(context, update.effective_chat.id),
        )
        return
    if data == "trip:reopen:confirm":
        trip = trip_repository.get_readable_trip(update.effective_chat.id)
        if trip is None:
            await query.answer("No trip")
            await query.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
            return
        try:
            reopened = trip_repository.reopen_trip(trip.id, update.effective_user.id)
        except ActiveTripExistsError:
            await query.answer("Active trip exists")
            await query.message.reply_text(DUPLICATE_TRIP_MESSAGE, reply_markup=active_menu())
            return
        await query.answer("Reopened")
        await query.message.reply_text(f"Reopened {reopened.name}. Expense edits are available again.", reply_markup=active_menu())
        return
    await query.answer("Trip action not found.")


def _looks_like_currency(value: str | None) -> bool:
    code = (value or "").strip()
    return len(code) == 3 and code.isalpha()

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


try:
    from telegram import KeyboardButton, ReplyKeyboardMarkup
except ImportError:  # pragma: no cover - tests use this lightweight fallback.

    @dataclass(frozen=True)
    class KeyboardButton:  # type: ignore[no-redef]
        text: str

    @dataclass(frozen=True)
    class ReplyKeyboardMarkup:  # type: ignore[no-redef]
        keyboard: list[list[str | KeyboardButton]]
        resize_keyboard: bool = True
        is_persistent: bool = True


SETUP_TRIP = "Set up trip"
ADD_EXPENSE = "Add expense"
BALANCES = "Balances"
PEOPLE = "People"
EXPENSES = "Expenses"
MEMBERS = "Members"
TRIP = "Trip"
HELP = "Help"
CANCEL = "Cancel"

SETUP_LABELS = {SETUP_TRIP, HELP}
ACTIVE_LABELS = {ADD_EXPENSE, BALANCES, PEOPLE, EXPENSES, MEMBERS, TRIP, HELP}
ALL_LABELS = SETUP_LABELS | ACTIVE_LABELS | {CANCEL}


def setup_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[SETUP_TRIP, HELP]], resize_keyboard=True, is_persistent=True)


def active_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [ADD_EXPENSE, BALANCES],
            [PEOPLE, EXPENSES],
            [MEMBERS, TRIP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def archived_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [SETUP_TRIP, TRIP],
            [BALANCES, HELP],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_for_chat(context: Any, chat_id: int) -> ReplyKeyboardMarkup:
    trip_repository = context.application.bot_data.get("trip_repository")
    if trip_repository is None:
        return setup_menu()
    if trip_repository.get_active_trip(chat_id) is not None:
        return active_menu()
    if trip_repository.get_readable_trip(chat_id) is not None:
        return archived_menu()
    return setup_menu()


def is_menu_label(text: str | None) -> bool:
    return (text or "").strip() in ALL_LABELS

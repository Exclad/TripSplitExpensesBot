from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:  # pragma: no cover

    @dataclass(frozen=True)
    class InlineKeyboardButton:  # type: ignore[no-redef]
        text: str
        callback_data: str

    @dataclass(frozen=True)
    class InlineKeyboardMarkup:  # type: ignore[no-redef]
        inline_keyboard: list[list[InlineKeyboardButton]]


HELP_OVERVIEW = (
    "TripSplitExpenses help\n"
    "/add 25 lunch - add an expense\n"
    "/balance - see who owes whom\n"
    "/trip - see trip status\n"
    "/members add Sam - add someone manually\n"
    "/members claim - link yourself to a manual member\n"
    "/refund and /correction - fix money after the fact\n"
    "/archive and /reopen - end or resume editing\n"
    "Use buttons for multiple payers, exact split, itemized meals, rate overrides, and details."
)

HELP_PAGES = {
    "add": (
        "Add expense\n"
        "Start with /add 25 lunch or /add 1930 JPY ramen. Pick a category, then use buttons for multiple payers, exact split, itemized meals, date edits, details, Save, or Cancel."
    ),
    "fix": (
        "Fix expense\n"
        "Open Details from a saved expense to edit, delete, or override the rate. Use /refund for money returned and /correction for small adjustments."
    ),
    "balances": (
        "See balances\n"
        "Use /balance for the settlement plan first. Buttons show person breakdown, category breakdown, expenses, and person-by-person audit rows."
    ),
    "members": (
        "Members\n"
        "Friends can tap Join this trip. Use /members add Sam for someone missing, then /members claim or /members map Sam to link Telegram later."
    ),
    "end": (
        "End trip\n"
        "Use /archive when the trip is done. The trip stays visible, balances still work, and edits are read-only until /reopen."
    ),
    "rates": (
        "Rates\n"
        "Foreign expenses keep the original amount and show the trip-currency amount. If a rate is missing or wrong, enter a custom rate or exact trip amount."
    ),
}


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Add expense", callback_data="help:add"),
                InlineKeyboardButton("Fix expense", callback_data="help:fix"),
            ],
            [
                InlineKeyboardButton("See balances", callback_data="help:balances"),
                InlineKeyboardButton("Members", callback_data="help:members"),
            ],
            [
                InlineKeyboardButton("End trip", callback_data="help:end"),
                InlineKeyboardButton("Rates", callback_data="help:rates"),
            ],
        ]
    )


async def help_command(update: Any, context: Any) -> None:
    await update.message.reply_text(HELP_OVERVIEW, reply_markup=help_keyboard())


async def help_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    data = query.data or ""
    page = data.removeprefix("help:")
    text = HELP_PAGES.get(page)
    if text is None:
        await query.answer("Help not found.")
        return
    await query.answer("Help")
    await query.message.reply_text(text, reply_markup=help_keyboard())

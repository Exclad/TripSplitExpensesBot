from __future__ import annotations

from typing import Any

from tripsplitexpenses.bot.handlers.balances import reply_balance_summary, reply_expense_list, reply_person_breakdown
from tripsplitexpenses.bot.handlers.expenses import exact_amount_message, start_button_expense
from tripsplitexpenses.bot.handlers.help import help_command
from tripsplitexpenses.bot.handlers.members import reply_members_overview
from tripsplitexpenses.bot.handlers.trips import setup_message, start_setup, trip_status
from tripsplitexpenses.bot.menu import ADD_EXPENSE, BALANCES, CANCEL, EXPENSES, HELP, MEMBERS, PEOPLE, SETUP_TRIP, TRIP, menu_for_chat


async def menu_command(update: Any, context: Any) -> None:
    await update.message.reply_text("Main buttons are ready.", reply_markup=menu_for_chat(context, update.effective_chat.id))


async def text_router(update: Any, context: Any) -> None:
    text = (update.message.text or "").strip()
    if text == CANCEL:
        context.application.bot_data.setdefault("trip_setup_drafts", {}).pop((update.effective_chat.id, update.effective_user.id), None)
        context.application.bot_data.setdefault("expense_drafts", {}).pop((update.effective_chat.id, update.effective_user.id), None)
        await update.message.reply_text("Cancelled. Use the buttons when you are ready.")
        return
    if await setup_message(update, context):
        return

    expense_drafts = context.application.bot_data.setdefault("expense_drafts", {})
    has_expense_draft = (update.effective_chat.id, update.effective_user.id) in expense_drafts
    if has_expense_draft:
        await exact_amount_message(update, context)
        return

    if text == SETUP_TRIP:
        await start_setup(update, context)
    elif text == ADD_EXPENSE:
        await start_button_expense(update, context)
    elif text == BALANCES:
        await reply_balance_summary(update, context)
    elif text == PEOPLE:
        await reply_person_breakdown(update, context)
    elif text == EXPENSES:
        await reply_expense_list(update, context)
    elif text == MEMBERS:
        await reply_members_overview(update, context)
    elif text == TRIP:
        await trip_status(update, context)
    elif text == HELP:
        await help_command(update, context)
    else:
        await exact_amount_message(update, context)

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from tripsplitexpenses.bot.copy import ARCHIVED_TRIP_READ_ONLY_MESSAGE, MISSING_TRIP_MESSAGE
from tripsplitexpenses.bot.formatters import format_confirmation, format_exchange_details, format_expense_history, format_payer_summary, format_saved_expense
from tripsplitexpenses.categories import BUILT_IN_CATEGORIES
from tripsplitexpenses.exchange import ExchangeRateProvider, convert_money, convert_with_exact_base, convert_with_manual_rate
from tripsplitexpenses.money import Money, MoneyError, auto_adjust_rounding, parse_money
from tripsplitexpenses.repositories.categories import CategoryRepository
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.bot.handlers.members import display_name_for_user
from tripsplitexpenses.bot.menu import active_menu, menu_for_chat
from tripsplitexpenses.bot.reply import force_reply
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


ADD_GUIDE_MESSAGE = "Tell me the amount and what it was for, like /add 25 lunch."
NO_MEMBERS_MESSAGE = "Add trip members first. Ask friends to tap Join this trip, or use /members add Sam."


def _drafts(context: Any) -> dict[tuple[int, int], dict]:
    return context.application.bot_data.setdefault("expense_drafts", {})


def _draft_key(update: Any) -> tuple[int, int]:
    return (update.effective_chat.id, update.effective_user.id)


def _exchange_provider(context: Any) -> ExchangeRateProvider:
    return context.application.bot_data.get("exchange_rate_provider") or ExchangeRateProvider()


def _expense_repository(context: Any) -> ExpenseRepository:
    repository = context.application.bot_data.get("expense_repository")
    if repository is None:
        repository = ExpenseRepository(context.application.bot_data["connection"])
        context.application.bot_data["expense_repository"] = repository
    return repository


def _category_repository(context: Any) -> CategoryRepository:
    repository = context.application.bot_data.get("category_repository")
    if repository is None:
        connection = context.application.bot_data.get("connection")
        if connection is None and context.application.bot_data.get("expense_repository") is not None:
            connection = context.application.bot_data["expense_repository"].connection
        repository = CategoryRepository(connection)
        context.application.bot_data["category_repository"] = repository
    return repository


def parse_add_args(text: str) -> tuple[str | None, str | None, str | None]:
    parts = text.split()
    args = parts[1:] if parts and parts[0].startswith("/add") else parts
    if len(args) < 2:
        return None, None, None
    amount = args[0]
    if len(args) >= 3 and len(args[1]) == 3 and args[1].isalpha():
        return amount, args[1].upper(), " ".join(args[2:]).strip()
    return amount, None, " ".join(args[1:]).strip()


def _is_plain_add_command(text: str) -> bool:
    parts = text.split()
    if len(parts) != 1:
        return False
    command = parts[0].split("@", 1)[0].lower()
    return command == "/add"


def category_keyboard(custom_categories: list[str] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(category, callback_data=f"expense:category:{category}")] for category in BUILT_IN_CATEGORIES]
    rows.extend(
        [InlineKeyboardButton(category, callback_data=f"expense:category:{category}")]
        for category in custom_categories or []
    )
    rows.append([InlineKeyboardButton("+ Custom", callback_data="expense:category-custom")])
    return InlineKeyboardMarkup(rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Save", callback_data="expense:save"), InlineKeyboardButton("Cancel", callback_data="expense:cancel")],
            [InlineKeyboardButton("Multiple payers", callback_data="expense:payers"), InlineKeyboardButton("Exact split", callback_data="expense:split:exact")],
            [InlineKeyboardButton("Itemize", callback_data="expense:itemize"), InlineKeyboardButton("Details", callback_data="expense:details")],
            [InlineKeyboardButton("Edit date", callback_data="expense:edit-date")],
        ]
    )


def saved_keyboard(expense_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Edit", callback_data=f"expense:edit:{expense_id}"), InlineKeyboardButton("Delete", callback_data=f"expense:delete:{expense_id}")],
            [InlineKeyboardButton("Details", callback_data=f"expense:details:{expense_id}")],
        ]
    )


def saved_details_keyboard(expense_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Override rate", callback_data=f"expense:override-rate:{expense_id}")],
            [InlineKeyboardButton("Home", callback_data="expense:home")],
        ]
    )


def exchange_override_keyboard(expense_id: str | None = None) -> InlineKeyboardMarkup:
    suffix = f":{expense_id}" if expense_id else ""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Enter rate", callback_data=f"expense:override-rate{suffix}"),
                InlineKeyboardButton("Enter trip amount", callback_data=f"expense:override-equivalent{suffix}"),
            ]
        ]
    )


def amount_currency_keyboard(base_currency: str, default_currency: str) -> InlineKeyboardMarkup | None:
    if base_currency == default_currency:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"Use {base_currency} instead", callback_data="expense:use-base-currency")]])


def member_toggle_keyboard(action_prefix: str, members: list[Member], selected_ids: set[str], done_callback: str) -> InlineKeyboardMarkup:
    rows = []
    for member in members:
        marker = "✓ " if member.id in selected_ids else ""
        rows.append([InlineKeyboardButton(f"{marker}{member.display_name}", callback_data=f"{action_prefix}:{member.id}")])
    rows.append([InlineKeyboardButton("Done", callback_data=done_callback)])
    return InlineKeyboardMarkup(rows)


async def _edit_or_reply_text(query: Any, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    edit_query = getattr(query, "edit_message_text", None)
    if callable(edit_query):
        await edit_query(text, reply_markup=reply_markup)
        return
    edit_message = getattr(query.message, "edit_text", None)
    if callable(edit_message):
        await edit_message(text, reply_markup=reply_markup)
        return
    await query.message.reply_text(text, reply_markup=reply_markup)


async def add_expense(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    readable_trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if readable_trip is not None and readable_trip.status == "archived":
        await update.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE)
        return
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    members = member_repository.list_members(trip.id)
    if not members:
        await update.message.reply_text(NO_MEMBERS_MESSAGE)
        return

    amount_text, currency, description = parse_add_args(update.message.text or "")
    if not amount_text or not description:
        if _is_plain_add_command(update.message.text or ""):
            await start_button_expense(update, context)
            return
        await update.message.reply_text(ADD_GUIDE_MESSAGE)
        return

    currency = currency or trip.base_currency
    try:
        original = parse_money(amount_text, currency)
    except MoneyError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply(f"Amount in {currency}"))
        return
    expense_date = date.today().isoformat()
    draft = {
        "trip_id": trip.id,
        "description": description,
        "expense_date": expense_date,
        "original_money": original,
        "split_method": "equal",
        "split_member_ids": [member.id for member in members],
        "created_by_telegram_id": update.effective_user.id,
        "created_by_display_name": display_name_for_user(update.effective_user),
        "exact_shares": {},
    }
    payer = _find_member_for_user(members, update.effective_user.id) or members[0]
    draft["payer_member_id"] = payer.id
    draft["payer_name"] = payer.display_name
    try:
        base, rate = convert_money(original, trip.base_currency, expense_date, _exchange_provider(context))
    except (LookupError, KeyError) as exc:
        draft["base_currency"] = trip.base_currency
        draft["flow"] = "entry_override_choice"
        _drafts(context)[_draft_key(update)] = draft
        await update.message.reply_text(
            f"I could not find an exchange rate for {original.currency}->{trip.base_currency} on {expense_date}.\n"
            f"You can enter the rate or the exact {trip.base_currency} amount instead.",
            reply_markup=exchange_override_keyboard(),
        )
        return
    except MoneyError as exc:
        await update.message.reply_text(str(exc))
        return
    draft["base_money"] = base
    draft["exchange_rate"] = rate
    _drafts(context)[_draft_key(update)] = draft
    custom_categories = [category.name for category in _category_repository(context).list_custom_categories(trip.id)]
    await update.message.reply_text("Pick a category.", reply_markup=category_keyboard(custom_categories))


async def start_button_expense(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    readable_trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if readable_trip is not None and readable_trip.status == "archived":
        await update.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE, reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    members = member_repository.list_members(trip.id)
    if not members:
        await update.message.reply_text(NO_MEMBERS_MESSAGE, reply_markup=active_menu())
        return
    payer = _find_member_for_user(members, update.effective_user.id) or members[0]
    draft = {
        "trip_id": trip.id,
        "base_currency": trip.base_currency,
        "entry_currency": trip.default_expense_currency,
        "expense_date": date.today().isoformat(),
        "split_method": "equal",
        "split_member_ids": [member.id for member in members],
        "created_by_telegram_id": update.effective_user.id,
        "created_by_display_name": display_name_for_user(update.effective_user),
        "payer_member_id": payer.id,
        "payer_name": payer.display_name,
        "exact_shares": {},
        "button_flow": True,
        "flow": "expense_amount",
    }
    _drafts(context)[_draft_key(update)] = draft
    currency_switch = amount_currency_keyboard(trip.base_currency, trip.default_expense_currency)
    if currency_switch is not None:
        await update.message.reply_text(
            f"How much was it? I will use {trip.default_expense_currency}.",
            reply_markup=currency_switch,
        )
        await update.message.reply_text(
            f"Send the amount in {trip.default_expense_currency}.",
            reply_markup=force_reply(f"Amount in {trip.default_expense_currency}"),
        )
        return
    await update.message.reply_text(
        f"How much was it? I will use {trip.default_expense_currency}.",
        reply_markup=force_reply(f"Amount in {trip.default_expense_currency}"),
    )


async def refund_command(update: Any, context: Any) -> None:
    await _start_adjustment(update, context, "refund")


async def correction_command(update: Any, context: Any) -> None:
    await _start_adjustment(update, context, "correction")


async def _start_adjustment(update: Any, context: Any, entry_type: str) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    readable_trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if readable_trip is not None and readable_trip.status == "archived":
        await update.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE)
        return
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    expenses = [expense for expense in _expense_repository(context).list_expenses(trip.id) if expense.entry_type == "expense"]
    if not expenses:
        await update.message.reply_text("No expenses to adjust yet.")
        return
    _drafts(context)[_draft_key(update)] = {
        "trip_id": trip.id,
        "flow": entry_type,
        "entry_type": entry_type,
        "created_by_telegram_id": update.effective_user.id,
    }
    rows = [[InlineKeyboardButton(expense.description, callback_data=f"expense:{entry_type}-pick:{expense.id}")] for expense in expenses[:10]]
    await update.message.reply_text(f"Which expense is this {entry_type} for?", reply_markup=InlineKeyboardMarkup(rows))


async def expense_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    data = query.data or ""
    draft = _drafts(context).get(_draft_key(update))
    if data == "expense:home":
        await query.answer("Home")
        await query.message.reply_text("Main buttons are ready.", reply_markup=menu_for_chat(context, update.effective_chat.id))
        return
    if data.startswith("expense:details:"):
        await _show_saved_details(query, context, data.rsplit(":", 1)[-1])
        return
    if data.startswith("expense:edit:"):
        if await _reply_if_archived_saved_expense(update, context, data.rsplit(":", 1)[-1]):
            return
        await _show_edit_picker(query, context, data.rsplit(":", 1)[-1])
        return
    if data.startswith("expense:delete:"):
        if await _reply_if_archived_saved_expense(update, context, data.rsplit(":", 1)[-1]):
            return
        await _confirm_delete(query, data.rsplit(":", 1)[-1])
        return
    if data.startswith("expense:delete-confirm:"):
        await _delete_saved_expense(update, context, data.rsplit(":", 1)[-1])
        return
    if data.startswith("expense:override-rate:"):
        await _start_saved_override(update, context, data.rsplit(":", 1)[-1], "saved_override_rate")
        return
    if data.startswith("expense:override-equivalent:"):
        await _start_saved_override(update, context, data.rsplit(":", 1)[-1], "saved_override_equivalent")
        return
    if data == "expense:override-rate":
        if draft is None:
            await query.answer("Start with /add.")
            return
        draft["flow"] = "entry_override_rate"
        await query.answer("Manual rate")
        await query.message.reply_text(
            f"Enter the rate: 1 {draft['original_money'].currency} = ? {draft['base_currency']}",
            reply_markup=force_reply("Exchange rate"),
        )
        return
    if data == "expense:override-equivalent":
        if draft is None:
            await query.answer("Start with /add.")
            return
        draft["flow"] = "entry_override_equivalent"
        await query.answer("Trip amount")
        await query.message.reply_text(
            f"Enter the exact {draft['base_currency']} amount.",
            reply_markup=force_reply(f"Amount in {draft['base_currency']}"),
        )
        return
    if data == "expense:use-base-currency":
        if draft is None:
            await query.answer("Start with Add expense.")
            return
        draft["entry_currency"] = draft["base_currency"]
        draft["flow"] = "expense_amount"
        await query.answer(f"Using {draft['base_currency']}")
        await query.message.reply_text(
            f"Okay, send the amount in {draft['base_currency']}.",
            reply_markup=force_reply(f"Amount in {draft['base_currency']}"),
        )
        return
    if data == "expense:delete-cancel":
        await query.answer("Cancelled")
        await query.message.reply_text("Cancelled. Nothing was deleted.")
        return
    if data.startswith("expense:edit-field:"):
        _, _, expense_id, field_name = data.split(":", 3)
        _drafts(context)[_draft_key(update)] = {"flow": "edit", "edit_expense_id": expense_id, "edit_field": field_name}
        await query.answer("Edit")
        await query.message.reply_text(f"Send the new {field_name}.", reply_markup=force_reply(f"New {field_name}"))
        return
    if draft is None:
        await query.answer("Start with /add.")
        return

    if data.startswith("expense:category:"):
        draft["category"] = data.rsplit(":", 1)[-1]
        await query.answer("Category set.")
        if draft.get("button_flow"):
            await _ask_split_members(query, context, draft)
        else:
            await _reply_confirmation(query, context, draft)
    elif data == "expense:category-custom":
        draft["flow"] = "custom_category"
        await query.answer("Custom category")
        await query.message.reply_text("What should the category be called?", reply_markup=force_reply("Category name"))
    elif data == "expense:save":
        await _save_draft(update, context, draft)
    elif data == "expense:cancel":
        _drafts(context).pop(_draft_key(update), None)
        await query.answer("Cancelled.")
        await query.message.reply_text("Cancelled. Nothing was saved.")
    elif data.startswith("expense:split-toggle:"):
        member_id = data.rsplit(":", 1)[-1]
        selected = set(draft.get("split_member_ids") or [])
        if member_id in selected:
            selected.remove(member_id)
        else:
            selected.add(member_id)
        draft["split_member_ids"] = list(selected)
        await query.answer("Updated")
        await _ask_split_members(query, context, draft, edit=True)
    elif data == "expense:split-done":
        if not draft.get("split_member_ids"):
            await query.answer("Choose at least one person.")
            return
        await query.answer("Split set")
        await _reply_confirmation(query, context, draft)
    elif data == "expense:details":
        await query.answer("Details")
        await query.message.reply_text(
            f"Rate: 1 {draft['original_money'].currency} = {draft['exchange_rate'].rate} {draft['base_money'].currency}\n"
            f"Rate date: {draft['exchange_rate'].date}\n"
            f"Source: {draft['exchange_rate'].provider}"
        )
    elif data == "expense:split:exact":
        draft["split_method"] = "exact"
        draft.pop("flow", None)
        draft["exact_index"] = 0
        draft["exact_shares"] = {}
        await query.answer("Exact split")
        await _ask_next_exact_amount(query, context, draft)
    elif data == "expense:payers":
        members = _all_members(context, draft)
        selected = {draft.get("payer_member_id")} if draft.get("payer_member_id") else set()
        draft["payer_member_ids"] = list(selected)
        await query.answer("Multiple payers")
        await query.message.reply_text(
            "Who paid?",
            reply_markup=member_toggle_keyboard("expense:payer-toggle", members, selected, "expense:payers-done"),
        )
    elif data.startswith("expense:payer-toggle:"):
        member_id = data.rsplit(":", 1)[-1]
        selected = set(draft.get("payer_member_ids") or [])
        if member_id in selected:
            selected.remove(member_id)
        else:
            selected.add(member_id)
        draft["payer_member_ids"] = list(selected)
        members = _all_members(context, draft)
        await query.answer("Updated")
        await _edit_or_reply_text(
            query,
            "Who paid?",
            member_toggle_keyboard("expense:payer-toggle", members, selected, "expense:payers-done"),
        )
    elif data == "expense:payers-done":
        if not draft.get("payer_member_ids"):
            await query.answer("Choose at least one payer.")
            return
        draft["flow"] = "payer_amounts"
        draft["payer_index"] = 0
        draft["payer_shares"] = {}
        await query.answer("Payers selected")
        await _ask_next_payer_amount(query, context, draft)
    elif data == "expense:itemize":
        draft["split_method"] = "itemized"
        draft["flow"] = "item_name"
        draft["itemized_lines"] = []
        draft["shared_charges"] = []
        await query.answer("Itemize")
        await query.message.reply_text("What is the first item?", reply_markup=force_reply("Item name"))
    elif data == "expense:item-add":
        draft["flow"] = "item_name"
        await query.answer("Add item")
        await query.message.reply_text("What is the item?", reply_markup=force_reply("Item name"))
    elif data.startswith("expense:item-member-toggle:"):
        member_id = data.rsplit(":", 1)[-1]
        selected = set(draft.get("current_item_member_ids") or [])
        if member_id in selected:
            selected.remove(member_id)
        else:
            selected.add(member_id)
        draft["current_item_member_ids"] = list(selected)
        await query.answer("Updated")
        await _reply_item_member_picker(query, context, draft, edit=True)
    elif data == "expense:item-members-done":
        if not draft.get("current_item_member_ids"):
            await query.answer("Choose at least one person.")
            return
        draft.setdefault("itemized_lines", []).append(
            {
                "name": draft.pop("current_item_name"),
                "base_amount_minor": draft.pop("current_item_amount_minor"),
                "member_ids": draft.pop("current_item_member_ids"),
            }
        )
        await query.answer("Item added")
        await _reply_itemized_next_step(query, draft)
    elif data == "expense:item-shared":
        draft["flow"] = "shared_charge_amount"
        await query.answer("Shared charge")
        await query.message.reply_text("How much are the shared charges?", reply_markup=force_reply("Shared charge amount"))
    elif data == "expense:item-done":
        await query.answer("Itemized")
        await _reply_itemized_confirmation(query, context, draft)
    elif data.startswith("expense:refund-pick:"):
        expense_id = data.rsplit(":", 1)[-1]
        draft["linked_expense_id"] = expense_id
        draft["flow"] = "refund_recipient"
        await query.answer("Expense selected")
        rows = [
            [InlineKeyboardButton(member.display_name, callback_data=f"expense:refund-recipient:{member.id}")]
            for member in _all_members(context, draft)
        ]
        await query.message.reply_text("Who received the refund?", reply_markup=InlineKeyboardMarkup(rows))
    elif data.startswith("expense:refund-recipient:"):
        draft["recipient_member_id"] = data.rsplit(":", 1)[-1]
        draft["flow"] = "refund_amount"
        await query.answer("Recipient selected")
        await query.message.reply_text("How much was refunded?", reply_markup=force_reply("Refund amount"))
    elif data.startswith("expense:correction-pick:"):
        draft["linked_expense_id"] = data.rsplit(":", 1)[-1]
        draft["flow"] = "correction_amount"
        await query.answer("Expense selected")
        await query.message.reply_text(
            "What is the correction amount? Use a minus sign for a reduction.",
            reply_markup=force_reply("Correction amount"),
        )
    elif data == "expense:auto-adjust":
        adjusted = auto_adjust_rounding(draft["base_money"].amount_minor, draft.get("exact_shares", {}))
        if adjusted is None:
            await query.answer("Too large to auto-adjust.")
            return
        draft["exact_shares"] = adjusted
        await query.answer("Adjusted.")
        await _reply_confirmation(query, context, draft)
    else:
        await query.answer("Coming in a later phase.")


async def exact_amount_message(update: Any, context: Any) -> None:
    draft = _drafts(context).get(_draft_key(update))
    if not draft:
        return
    if draft.get("flow") == "expense_amount":
        await _button_expense_amount_message(update, context, draft)
        return
    if draft.get("flow") == "expense_description":
        await _button_expense_description_message(update, context, draft)
        return
    if draft.get("flow") == "custom_category":
        await _custom_category_message(update, context, draft)
        return
    if draft.get("flow") == "payer_amounts":
        await _payer_amount_message(update, context, draft)
        return
    if draft.get("flow") in {"item_name", "item_amount", "shared_charge_amount"}:
        await _itemized_message(update, context, draft)
        return
    if draft.get("flow") == "edit":
        await _edit_message(update, context, draft)
        return
    if draft.get("flow") in {"refund_amount", "correction_amount", "correction_note"}:
        await _adjustment_message(update, context, draft)
        return
    if draft.get("flow") in {"entry_override_rate", "entry_override_equivalent"}:
        await _entry_override_message(update, context, draft)
        return
    if draft.get("flow") in {"saved_override_rate", "saved_override_equivalent"}:
        await _saved_override_message(update, context, draft)
        return
    if draft.get("split_method") != "exact" or "exact_index" not in draft:
        return
    members = _selected_members(context, draft)
    index = draft["exact_index"]
    if index >= len(members):
        return
    member = members[index]
    try:
        amount = parse_money(update.message.text or "", draft["base_money"].currency)
    except MoneyError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply(f"Amount for {member.display_name}"))
        return
    draft["exact_shares"][member.id] = amount.amount_minor
    draft["exact_index"] = index + 1
    if draft["exact_index"] < len(members):
        next_member = members[draft["exact_index"]]
        await update.message.reply_text(
            f"How much for {next_member.display_name}?",
            reply_markup=force_reply(f"Amount for {next_member.display_name}"),
        )
        return
    difference = draft["base_money"].amount_minor - sum(draft["exact_shares"].values())
    if difference:
        entered = sum(draft["exact_shares"].values())
        text = (
            f"Split total does not match. Expected {draft['base_money'].amount_minor} cents, "
            f"entered {entered} cents, difference {difference} cents."
        )
        buttons = []
        if abs(difference) == 1:
            buttons.append([InlineKeyboardButton("Auto-adjust 1 cent", callback_data="expense:auto-adjust")])
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        return
    await update.message.reply_text(format_confirmation(draft, members), reply_markup=confirmation_keyboard())


async def _save_draft(update: Any, context: Any, draft: dict) -> None:
    query = update.callback_query
    expense_repository = _expense_repository(context)
    if draft["split_method"] == "exact":
        exact_shares = draft.get("exact_shares") or {}
        difference = draft["base_money"].amount_minor - sum(exact_shares.values())
        if difference:
            await query.answer("Fix split total first.")
            await query.message.reply_text(
                f"Split total does not match. Expected {draft['base_money'].amount_minor} cents, "
                f"entered {sum(exact_shares.values())} cents, difference {difference} cents."
            )
            return
    else:
        exact_shares = None

    expense = expense_repository.create_expense(
        trip_id=draft["trip_id"],
        description=draft["description"],
        category=draft["category"],
        expense_date=draft["expense_date"],
        split_method=draft["split_method"],
        original_amount_minor=draft["original_money"].amount_minor,
        original_currency=draft["original_money"].currency,
        base_amount_minor=draft["base_money"].amount_minor,
        base_currency=draft["base_money"].currency,
        exchange_rate=draft["exchange_rate"],
        payer_member_id=draft["payer_member_id"],
        payer_shares=draft.get("payer_shares") or None,
        split_member_ids=draft["split_member_ids"],
        exact_shares=exact_shares,
        itemized_lines=draft.get("itemized_lines"),
        shared_charges=draft.get("shared_charges"),
        custom_categories=[category.name for category in _category_repository(context).list_custom_categories(draft["trip_id"])],
        created_by_telegram_id=draft["created_by_telegram_id"],
        actor_display_name=draft.get("created_by_display_name"),
    )
    members = _selected_members(context, draft)
    payer_names = _payer_names(context, draft)
    _drafts(context).pop(_draft_key(update), None)
    await query.answer("Saved.")
    await query.message.reply_text(
        format_saved_expense(expense, format_payer_summary(payer_names), len(members)),
        reply_markup=saved_keyboard(expense.id),
    )


async def _reply_confirmation(query: Any, context: Any, draft: dict) -> None:
    await query.message.reply_text(format_confirmation(draft, _selected_members(context, draft)), reply_markup=confirmation_keyboard())


async def _ask_next_exact_amount(query: Any, context: Any, draft: dict) -> None:
    members = _selected_members(context, draft)
    if not members:
        await query.message.reply_text("Choose at least one person for the split.")
        return
    await query.message.reply_text(
        f"How much for {members[0].display_name}?",
        reply_markup=force_reply(f"Amount for {members[0].display_name}"),
    )


async def _ask_next_payer_amount(query: Any, context: Any, draft: dict) -> None:
    payers = _selected_payers(context, draft)
    if not payers:
        await query.message.reply_text("Choose at least one payer.")
        return
    await query.message.reply_text(
        f"How much did {payers[0].display_name} pay?",
        reply_markup=force_reply(f"Paid by {payers[0].display_name}"),
    )


async def _payer_amount_message(update: Any, context: Any, draft: dict) -> None:
    payers = _selected_payers(context, draft)
    index = draft.get("payer_index", 0)
    if index >= len(payers):
        return
    member = payers[index]
    try:
        amount = parse_money(update.message.text or "", draft["original_money"].currency)
    except MoneyError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply(f"Paid by {member.display_name}"))
        return
    draft["payer_shares"][member.id] = amount.amount_minor
    draft["payer_index"] = index + 1
    if draft["payer_index"] < len(payers):
        next_payer = payers[draft["payer_index"]]
        await update.message.reply_text(
            f"How much did {next_payer.display_name} pay?",
            reply_markup=force_reply(f"Paid by {next_payer.display_name}"),
        )
        return
    difference = draft["original_money"].amount_minor - sum(draft["payer_shares"].values())
    if difference:
        entered = sum(draft["payer_shares"].values())
        await update.message.reply_text(
            f"Payer total does not match. Expected {draft['original_money'].amount_minor} cents, "
            f"entered {entered} cents, difference {difference} cents."
        )
        return
    draft.pop("flow", None)
    draft["payer_summary"] = format_payer_summary([payer.display_name for payer in payers])
    await update.message.reply_text(format_confirmation(draft, _selected_members(context, draft)), reply_markup=confirmation_keyboard())


async def _custom_category_message(update: Any, context: Any, draft: dict) -> None:
    try:
        category = _category_repository(context).create_category(
            draft["trip_id"],
            update.message.text or "",
            update.effective_user.id,
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply("Category name"))
        return
    draft["category"] = category.name
    draft.pop("flow", None)
    await update.message.reply_text(format_confirmation(draft, _selected_members(context, draft)), reply_markup=confirmation_keyboard())


async def _itemized_message(update: Any, context: Any, draft: dict) -> None:
    if draft["flow"] == "item_name":
        name = (update.message.text or "").strip()
        if not name:
            await update.message.reply_text("Enter an item name.", reply_markup=force_reply("Item name"))
            return
        draft["current_item_name"] = name
        draft["flow"] = "item_amount"
        await update.message.reply_text(f"How much was {name}?", reply_markup=force_reply(f"Amount for {name}"))
        return
    if draft["flow"] == "item_amount":
        try:
            amount = parse_money(update.message.text or "", draft["base_money"].currency)
        except MoneyError as exc:
            await update.message.reply_text(str(exc), reply_markup=force_reply("Item amount"))
            return
        draft["current_item_amount_minor"] = amount.amount_minor
        draft["current_item_member_ids"] = []
        draft["flow"] = "item_members"
        await update.message.reply_text(
            "Who shared this item?",
            reply_markup=member_toggle_keyboard(
                "expense:item-member-toggle",
                _all_members(context, draft),
                set(),
                "expense:item-members-done",
            ),
        )
        return
    if draft["flow"] == "shared_charge_amount":
        try:
            amount = parse_money(update.message.text or "", draft["base_money"].currency)
        except MoneyError as exc:
            await update.message.reply_text(str(exc), reply_markup=force_reply("Shared charge amount"))
            return
        draft.setdefault("shared_charges", []).append({"name": "Shared charges", "base_amount_minor": amount.amount_minor})
        draft.pop("flow", None)
        await update.message.reply_text("Shared charges added.", reply_markup=_itemized_next_keyboard(draft))


async def _edit_message(update: Any, context: Any, draft: dict) -> None:
    if await _reply_if_archived_saved_expense(update, context, draft["edit_expense_id"]):
        return
    field_name = draft["edit_field"]
    value = update.message.text or ""
    kwargs: dict[str, str] = {}
    if field_name == "description":
        kwargs["description"] = value
    elif field_name == "category":
        expense = _expense_repository(context).get_expense(draft["edit_expense_id"])
        if expense is None:
            await update.message.reply_text("Expense not found.")
            return
        kwargs["category"] = value
        kwargs["custom_categories"] = [category.name for category in _category_repository(context).list_custom_categories(expense.trip_id)]
    elif field_name == "date":
        kwargs["expense_date"] = value
    else:
        kwargs["note"] = value
    try:
        updated = _expense_repository(context).update_expense(
            draft["edit_expense_id"],
            **kwargs,
            updated_by_telegram_id=update.effective_user.id,
            actor_display_name=display_name_for_user(update.effective_user),
        )
    except ValueError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply(f"New {field_name}"))
        return
    _drafts(context).pop(_draft_key(update), None)
    await update.message.reply_text(f"Updated: {updated.description}")


async def _adjustment_message(update: Any, context: Any, draft: dict) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    readable_trip = trip_repository.get_readable_trip(update.effective_chat.id)
    if readable_trip is not None and readable_trip.status == "archived":
        await update.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE)
        return
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    if draft["flow"] == "refund_amount":
        try:
            money = parse_money(update.message.text or "", trip.base_currency)
        except MoneyError as exc:
            await update.message.reply_text(str(exc), reply_markup=force_reply("Refund amount"))
            return
        rate = _exchange_provider(context).get_rate(trip.base_currency, trip.base_currency, date.today().isoformat())
        expense = _expense_repository(context).create_refund(
            original_expense_id=draft["linked_expense_id"],
            recipient_member_id=draft["recipient_member_id"],
            amount_minor=money.amount_minor,
            currency=money.currency,
            base_amount_minor=money.amount_minor,
            base_currency=money.currency,
            exchange_rate=rate,
            expense_date=date.today().isoformat(),
            created_by_telegram_id=update.effective_user.id,
            actor_display_name=display_name_for_user(update.effective_user),
        )
        _drafts(context).pop(_draft_key(update), None)
        await update.message.reply_text(format_saved_expense(expense, "refund", 1), reply_markup=saved_keyboard(expense.id))
        return
    if draft["flow"] == "correction_amount":
        raw = (update.message.text or "").strip()
        sign = -1 if raw.startswith("-") else 1
        try:
            money = parse_money(raw.removeprefix("-"), trip.base_currency)
        except MoneyError as exc:
            await update.message.reply_text(str(exc), reply_markup=force_reply("Correction amount"))
            return
        draft["correction_amount_minor"] = money.amount_minor * sign
        draft["correction_currency"] = money.currency
        draft["flow"] = "correction_note"
        await update.message.reply_text("What is the correction for?", reply_markup=force_reply("Correction note"))
        return
    if draft["flow"] == "correction_note":
        member = _find_member_for_user(_all_members(context, draft), update.effective_user.id) or _all_members(context, draft)[0]
        amount_minor = draft["correction_amount_minor"]
        rate = _exchange_provider(context).get_rate(trip.base_currency, trip.base_currency, date.today().isoformat())
        expense = _expense_repository(context).create_correction(
            original_expense_id=draft["linked_expense_id"],
            amount_minor=amount_minor,
            currency=draft["correction_currency"],
            base_amount_minor=amount_minor,
            base_currency=draft["correction_currency"],
            exchange_rate=rate,
            expense_date=date.today().isoformat(),
            note=update.message.text or "Correction",
            member_id=member.id,
            created_by_telegram_id=update.effective_user.id,
            actor_display_name=display_name_for_user(update.effective_user),
        )
        _drafts(context).pop(_draft_key(update), None)
        await update.message.reply_text(format_saved_expense(expense, "correction", 1), reply_markup=saved_keyboard(expense.id))


async def _entry_override_message(update: Any, context: Any, draft: dict) -> None:
    try:
        if draft["flow"] == "entry_override_rate":
            base, rate = convert_with_manual_rate(
                draft["original_money"],
                draft["base_currency"],
                Decimal((update.message.text or "").strip()),
                draft["expense_date"],
            )
        else:
            base_money = parse_money(update.message.text or "", draft["base_currency"])
            base, rate = convert_with_exact_base(draft["original_money"], base_money, draft["expense_date"])
    except (ValueError, MoneyError) as exc:
        if draft["flow"] == "entry_override_rate":
            await update.message.reply_text(str(exc), reply_markup=force_reply("Exchange rate"))
        else:
            await update.message.reply_text(str(exc), reply_markup=force_reply(f"Amount in {draft['base_currency']}"))
        return
    draft["base_money"] = base
    draft["exchange_rate"] = rate
    draft.pop("flow", None)
    if draft.get("button_flow") and not draft.get("description"):
        draft["flow"] = "expense_description"
        await update.message.reply_text("What was it for?", reply_markup=force_reply("Description"))
    else:
        custom_categories = [category.name for category in _category_repository(context).list_custom_categories(draft["trip_id"])]
        await update.message.reply_text("Pick a category.", reply_markup=category_keyboard(custom_categories))


async def _button_expense_amount_message(update: Any, context: Any, draft: dict) -> None:
    currency = draft["entry_currency"]
    try:
        original = parse_money(update.message.text or "", currency)
    except MoneyError as exc:
        await update.message.reply_text(str(exc), reply_markup=force_reply(f"Amount in {currency}"))
        return
    draft["original_money"] = original
    if original.currency == draft["base_currency"]:
        base, rate = convert_money(original, draft["base_currency"], draft["expense_date"], _exchange_provider(context))
        draft["base_money"] = base
        draft["exchange_rate"] = rate
    draft["flow"] = "expense_description"
    await update.message.reply_text("What was it for?", reply_markup=force_reply("Description"))


async def _button_expense_description_message(update: Any, context: Any, draft: dict) -> None:
    description = (update.message.text or "").strip()
    if not description:
        await update.message.reply_text("Send a short description, like lunch.", reply_markup=force_reply("Description"))
        return
    draft["description"] = description
    if "base_money" not in draft:
        if not await _convert_button_expense_amount(update, context, draft):
            return
    draft.pop("flow", None)
    custom_categories = [category.name for category in _category_repository(context).list_custom_categories(draft["trip_id"])]
    await update.message.reply_text("Pick a category.", reply_markup=category_keyboard(custom_categories))


async def _convert_button_expense_amount(update: Any, context: Any, draft: dict) -> bool:
    original = draft["original_money"]
    try:
        base, rate = convert_money(original, draft["base_currency"], draft["expense_date"], _exchange_provider(context))
    except (LookupError, KeyError):
        draft["flow"] = "entry_override_choice"
        await update.message.reply_text(
            f"I could not find an exchange rate for {original.currency}->{draft['base_currency']} on {draft['expense_date']}.\n"
            f"You can enter the rate or the exact {draft['base_currency']} amount instead.",
            reply_markup=exchange_override_keyboard(),
        )
        return False
    except MoneyError as exc:
        await update.message.reply_text(str(exc))
        return False
    draft["base_money"] = base
    draft["exchange_rate"] = rate
    return True


async def _ask_split_members(query: Any, context: Any, draft: dict, *, edit: bool = False) -> None:
    members = _all_members(context, draft)
    keyboard = member_toggle_keyboard(
        "expense:split-toggle",
        members,
        set(draft.get("split_member_ids") or []),
        "expense:split-done",
    )
    if edit:
        await _edit_or_reply_text(query, "Who should split this?", keyboard)
    else:
        await query.message.reply_text("Who should split this?", reply_markup=keyboard)


async def _start_saved_override(update: Any, context: Any, expense_id: str, flow: str) -> None:
    query = update.callback_query
    if await _reply_if_archived_saved_expense(update, context, expense_id):
        return
    expense = _expense_repository(context).get_expense(expense_id)
    if expense is None:
        await query.answer("Expense not found.")
        return
    _drafts(context)[_draft_key(update)] = {"flow": flow, "override_expense_id": expense_id}
    await query.answer("Override rate")
    if flow == "saved_override_rate":
        await query.message.reply_text(
            f"Enter the rate: 1 {expense.original_currency} = ? {expense.base_currency}",
            reply_markup=force_reply("Exchange rate"),
        )
    else:
        await query.message.reply_text(
            f"Enter the exact {expense.base_currency} amount.",
            reply_markup=force_reply(f"Amount in {expense.base_currency}"),
        )


async def _saved_override_message(update: Any, context: Any, draft: dict) -> None:
    expense = _expense_repository(context).get_expense(draft["override_expense_id"])
    if expense is None:
        await update.message.reply_text("Expense not found.")
        return
    if await _reply_if_archived_saved_expense(update, context, expense.id):
        return
    original = Money(expense.original_amount_minor, expense.original_currency)
    try:
        if draft["flow"] == "saved_override_rate":
            base, rate = convert_with_manual_rate(original, expense.base_currency, Decimal((update.message.text or "").strip()), expense.expense_date)
        else:
            base_money = parse_money(update.message.text or "", expense.base_currency)
            base, rate = convert_with_exact_base(original, base_money, expense.expense_date)
    except (ValueError, MoneyError) as exc:
        if draft["flow"] == "saved_override_rate":
            await update.message.reply_text(str(exc), reply_markup=force_reply("Exchange rate"))
        else:
            await update.message.reply_text(str(exc), reply_markup=force_reply(f"Amount in {expense.base_currency}"))
        return
    updated = _expense_repository(context).override_exchange_rate(
        expense.id,
        base_amount_minor=base.amount_minor,
        exchange_rate=rate,
        overridden_by_telegram_id=update.effective_user.id,
        actor_display_name=display_name_for_user(update.effective_user),
    )
    _drafts(context).pop(_draft_key(update), None)
    await update.message.reply_text(f"Updated rate for {updated.description}.")


async def _reply_item_member_picker(query: Any, context: Any, draft: dict, *, edit: bool = False) -> None:
    keyboard = member_toggle_keyboard(
        "expense:item-member-toggle",
        _all_members(context, draft),
        set(draft.get("current_item_member_ids") or []),
        "expense:item-members-done",
    )
    if edit:
        await _edit_or_reply_text(query, "Who shared this item?", keyboard)
    else:
        await query.message.reply_text("Who shared this item?", reply_markup=keyboard)


def _itemized_next_keyboard(draft: dict) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Add item", callback_data="expense:item-add"), InlineKeyboardButton("Shared charges", callback_data="expense:item-shared")],
        [InlineKeyboardButton("Done itemizing", callback_data="expense:item-done")],
    ]
    if len(draft.get("itemized_lines") or []) >= 3:
        rows.append([InlineKeyboardButton("Use exact split instead", callback_data="expense:split:exact")])
    return InlineKeyboardMarkup(rows)


async def _reply_itemized_next_step(query: Any, draft: dict) -> None:
    count = len(draft.get("itemized_lines") or [])
    await query.message.reply_text(f"Added item {count}.", reply_markup=_itemized_next_keyboard(draft))


async def _reply_itemized_confirmation(query: Any, context: Any, draft: dict) -> None:
    entered = sum(line["base_amount_minor"] for line in draft.get("itemized_lines", [])) + sum(
        charge["base_amount_minor"] for charge in draft.get("shared_charges", [])
    )
    expected = draft["base_money"].amount_minor
    if entered != expected:
        await query.message.reply_text(
            f"Itemized total does not match. Expected {expected} cents, entered {entered} cents, difference {expected - entered} cents.",
            reply_markup=_itemized_next_keyboard(draft),
        )
        return
    draft.pop("flow", None)
    await _reply_confirmation(query, context, draft)


async def _show_saved_details(query: Any, context: Any, expense_id: str) -> None:
    expense = _expense_repository(context).get_expense(expense_id)
    if expense is None:
        await query.answer("Expense not found.")
        return
    await query.answer("Details")
    members = _member_name_map(context, expense.trip_id)
    payer_lines = [
        f"- {members.get(payer.member_id, payer.member_id)}: {Money(payer.amount_minor, payer.currency).amount}"
        for payer in expense.payers
    ]
    extra = "\nPayers:\n" + "\n".join(payer_lines) if payer_lines else ""
    if expense.linked_expense_id:
        extra += f"\nLinked to: {expense.linked_expense_id}"
    if expense.note:
        extra += f"\nNote: {expense.note}"
    if expense.line_items:
        extra += "\nItems:\n" + "\n".join(f"- {line.name}: {Money(line.base_amount_minor, expense.base_currency).amount}" for line in expense.line_items)
    if expense.shared_charges:
        extra += "\nShared charges:\n" + "\n".join(
            f"- {charge.name}: {Money(charge.base_amount_minor, expense.base_currency).amount}" for charge in expense.shared_charges
        )
    history = format_expense_history(
        _expense_repository(context).list_audit_events(expense.id),
        _actor_name_map(context, expense.trip_id),
    )
    await query.message.reply_text(
        format_exchange_details(expense) + extra + "\n\n" + history,
        reply_markup=saved_details_keyboard(expense.id),
    )


async def _show_edit_picker(query: Any, context: Any, expense_id: str) -> None:
    if _expense_repository(context).get_expense(expense_id) is None:
        await query.answer("Expense not found.")
        return
    await query.answer("Edit")
    await query.message.reply_text(
        "What do you want to edit?",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Description", callback_data=f"expense:edit-field:{expense_id}:description")],
                [InlineKeyboardButton("Category", callback_data=f"expense:edit-field:{expense_id}:category")],
                [InlineKeyboardButton("Date", callback_data=f"expense:edit-field:{expense_id}:date")],
                [InlineKeyboardButton("Note", callback_data=f"expense:edit-field:{expense_id}:note")],
            ]
        ),
    )


async def _confirm_delete(query: Any, expense_id: str) -> None:
    await query.answer("Confirm delete")
    await query.message.reply_text(
        "Delete this expense?",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Delete", callback_data=f"expense:delete-confirm:{expense_id}"), InlineKeyboardButton("Cancel", callback_data="expense:delete-cancel")]]
        ),
    )


async def _delete_saved_expense(update: Any, context: Any, expense_id: str) -> None:
    query = update.callback_query
    if await _reply_if_archived_saved_expense(update, context, expense_id):
        return
    _expense_repository(context).delete_expense(expense_id, update.effective_user.id, actor_display_name=display_name_for_user(update.effective_user))
    await query.answer("Deleted")
    await query.message.reply_text("Deleted. It will no longer show in expense lists.")


def _selected_members(context: Any, draft: dict) -> list[Member]:
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    members = member_repository.list_members(draft["trip_id"])
    selected = set(draft.get("split_member_ids", []))
    return [member for member in members if member.id in selected]


def _all_members(context: Any, draft: dict) -> list[Member]:
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    return member_repository.list_members(draft["trip_id"])


def _selected_payers(context: Any, draft: dict) -> list[Member]:
    selected = set(draft.get("payer_member_ids") or [])
    return [member for member in _all_members(context, draft) if member.id in selected]


def _payer_names(context: Any, draft: dict) -> list[str]:
    if draft.get("payer_shares"):
        selected = set(draft["payer_shares"])
        return [member.display_name for member in _all_members(context, draft) if member.id in selected]
    return [draft.get("payer_name", "You")]


def _member_name_map(context: Any, trip_id: str) -> dict[str, str]:
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    return {member.id: member.display_name for member in member_repository.list_members(trip_id)}


def _actor_name_map(context: Any, trip_id: str) -> dict[int, str]:
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    return {
        member.telegram_user_id: member.display_name
        for member in member_repository.list_members(trip_id)
        if member.telegram_user_id is not None
    }


def _find_member_for_user(members: list[Member], telegram_user_id: int) -> Member | None:
    return next((member for member in members if member.telegram_user_id == telegram_user_id), None)


async def _reply_if_archived_saved_expense(update: Any, context: Any, expense_id: str) -> bool:
    expense = _expense_repository(context).get_expense(expense_id)
    if expense is None:
        return False
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_trip(expense.trip_id)
    if trip is None or trip.status != "archived":
        return False
    if getattr(update, "callback_query", None) is not None:
        await update.callback_query.answer("Archived")
        await update.callback_query.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE)
    else:
        await update.message.reply_text(ARCHIVED_TRIP_READ_ONLY_MESSAGE)
    return True

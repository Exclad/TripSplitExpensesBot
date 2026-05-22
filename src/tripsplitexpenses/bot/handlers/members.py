from __future__ import annotations

from typing import Any

from tripsplitexpenses.bot.copy import (
    JOIN_CALLBACK_DATA,
    JOIN_SUCCESS_MESSAGE,
    MANUAL_ADD_SUCCESS_TEMPLATE,
    MEMBER_MAPPING_CONFIRM_TEMPLATE,
    MEMBER_MAPPING_SUCCESS_TEMPLATE,
    MISSING_TRIP_MESSAGE,
)
from tripsplitexpenses.repositories.members import MemberRepository
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


def display_name_for_user(user: Any) -> str:
    full_name = getattr(user, "full_name", None)
    if full_name:
        return str(full_name)
    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    name = " ".join(part for part in [first_name, last_name] if part)
    return name or getattr(user, "username", None) or f"Telegram user {user.id}"


async def join_trip_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    if query.data != JOIN_CALLBACK_DATA:
        return

    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await query.answer("No active trip yet.")
        await query.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    user = update.effective_user
    member_repository.join_from_telegram_user(
        trip_id=trip.id,
        telegram_user_id=user.id,
        username=getattr(user, "username", None),
        display_name=display_name_for_user(user),
        created_by_telegram_id=user.id,
    )
    await query.answer(JOIN_SUCCESS_MESSAGE)
    await query.message.reply_text(JOIN_SUCCESS_MESSAGE)


async def members_command(update: Any, context: Any) -> None:
    text = update.message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) >= 2 and parts[1].lower() == "claim":
        await _reply_claim_options(update, context)
        return
    if len(parts) >= 3 and parts[1].lower() == "map" and parts[2].strip():
        await _reply_map_confirmation(update, context, parts[2].strip())
        return
    if len(parts) < 3 or parts[1].lower() != "add" or not parts[2].strip():
        await update.message.reply_text("Use /members add Sam, /members claim, or /members map Sam.")
        return

    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    member = member_repository.add_manual_member(
        trip_id=trip.id,
        display_name=parts[2].strip(),
        created_by_telegram_id=update.effective_user.id,
    )
    await update.message.reply_text(MANUAL_ADD_SUCCESS_TEMPLATE.format(name=member.display_name))


async def member_callback(update: Any, context: Any) -> None:
    query = update.callback_query
    data = query.data or ""
    if data == "members:map-cancel":
        await query.answer("Cancelled")
        await query.message.reply_text("Cancelled. Nothing changed.")
        return
    if not data.startswith("members:map-confirm:"):
        await query.answer("Member action not found.")
        return
    member_id = data.rsplit(":", 1)[-1]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    user = update.effective_user
    try:
        mapped = member_repository.map_manual_member_to_telegram(
            member_id=member_id,
            telegram_user_id=user.id,
            username=getattr(user, "username", None),
            mapped_by_telegram_id=user.id,
        )
    except ValueError as exc:
        await query.answer("Not linked")
        await query.message.reply_text(str(exc))
        return
    await query.answer("Linked")
    await query.message.reply_text(MEMBER_MAPPING_SUCCESS_TEMPLATE.format(name=mapped.display_name))


async def _reply_claim_options(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    manual_members = member_repository.list_unmapped_manual_members(trip.id)
    if not manual_members:
        await update.message.reply_text("No unmapped manual members yet.")
        return
    rows = [[InlineKeyboardButton(member.display_name, callback_data=f"members:map-confirm:{member.id}")] for member in manual_members]
    await update.message.reply_text("Which person are you?", reply_markup=InlineKeyboardMarkup(rows))


async def _reply_map_confirmation(update: Any, context: Any, display_name: str) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    member_repository: MemberRepository = context.application.bot_data["member_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return
    member = member_repository.find_by_display_name(trip.id, display_name)
    if member is None:
        await update.message.reply_text("I could not find that member. Try /members claim to see unmapped people.")
        return
    if member.telegram_user_id is not None:
        await update.message.reply_text("That member is already linked to Telegram.")
        return
    await update.message.reply_text(
        MEMBER_MAPPING_CONFIRM_TEMPLATE.format(name=member.display_name),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Link me", callback_data=f"members:map-confirm:{member.id}"),
                    InlineKeyboardButton("Cancel", callback_data="members:map-cancel"),
                ]
            ]
        ),
    )

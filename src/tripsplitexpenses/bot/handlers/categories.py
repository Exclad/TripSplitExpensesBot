from __future__ import annotations

from typing import Any

from tripsplitexpenses.bot.copy import MISSING_TRIP_MESSAGE
from tripsplitexpenses.repositories.categories import CategoryRepository
from tripsplitexpenses.repositories.trips import TripRepository


def _category_repository(context: Any) -> CategoryRepository:
    repository = context.application.bot_data.get("category_repository")
    if repository is None:
        connection = context.application.bot_data.get("connection")
        if connection is None and context.application.bot_data.get("expense_repository") is not None:
            connection = context.application.bot_data["expense_repository"].connection
        repository = CategoryRepository(connection)
        context.application.bot_data["category_repository"] = repository
    return repository


async def categories_command(update: Any, context: Any) -> None:
    trip_repository: TripRepository = context.application.bot_data["trip_repository"]
    trip = trip_repository.get_active_trip(update.effective_chat.id)
    if trip is None:
        await update.message.reply_text(MISSING_TRIP_MESSAGE)
        return

    repository = _category_repository(context)
    parts = (update.message.text or "").split()
    action = parts[1].lower() if len(parts) > 1 else "list"
    try:
        if action == "add" and len(parts) >= 3:
            category = repository.create_category(trip.id, " ".join(parts[2:]), update.effective_user.id)
            await update.message.reply_text(f"Added category: {category.name}")
        elif action == "rename" and len(parts) >= 4:
            categories = repository.list_custom_categories(trip.id)
            old_name = parts[2].lower()
            match = next((category for category in categories if category.name.lower() == old_name), None)
            if match is None:
                await update.message.reply_text("Category not found.")
                return
            renamed = repository.rename_category(match.id, " ".join(parts[3:]))
            await update.message.reply_text(f"Renamed category to: {renamed.name}")
        elif action == "delete" and len(parts) >= 3:
            categories = repository.list_custom_categories(trip.id)
            name = " ".join(parts[2:]).lower()
            match = next((category for category in categories if category.name.lower() == name), None)
            if match is None:
                await update.message.reply_text("Category not found.")
                return
            repository.delete_category(match.id, update.effective_user.id)
            await update.message.reply_text(f"Deleted category: {match.name}")
        else:
            names = repository.list_category_names(trip.id)
            await update.message.reply_text("Categories:\n" + "\n".join(f"- {name}" for name in names))
    except ValueError as exc:
        await update.message.reply_text(str(exc))

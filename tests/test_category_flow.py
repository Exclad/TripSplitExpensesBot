from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.handlers.categories import categories_command
from tripsplitexpenses.bot.handlers.expenses import add_expense, exact_amount_message, expense_callback
from tripsplitexpenses.exchange import FixedExchangeRateProvider
from tripsplitexpenses.repositories.categories import CategoryRepository


def _context(trip_repository, member_repository, expense_repository):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=FixedExchangeRateProvider({}),
    )


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    member_repository.add_manual_member(trip.id, "Sam", 101)
    return trip


async def test_custom_category_during_add_returns_to_confirmation(trip_repository, member_repository, expense_repository):
    trip = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 8 coffee", user=fake_user(101, "Alex", "Alex")), context)
    custom = fake_callback_update("expense:category-custom", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(custom, context)
    assert "category" in custom.callback_query.message.replies[0]["text"].lower()

    message = fake_message_update("Coffee", user=fake_user(101, "Alex", "Alex"))
    await exact_amount_message(message, context)

    assert "Category: Coffee" in message.message.replies[0]["text"]
    assert "Coffee" in CategoryRepository(expense_repository.connection).list_category_names(trip.id)


async def test_categories_command_manages_trip_categories(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)

    add = fake_message_update("/categories add Coffee", user=fake_user(101, "Alex", "Alex"))
    await categories_command(add, context)
    rename = fake_message_update("/categories rename Coffee Dessert", user=fake_user(101, "Alex", "Alex"))
    await categories_command(rename, context)
    delete = fake_message_update("/categories delete Dessert", user=fake_user(101, "Alex", "Alex"))
    await categories_command(delete, context)

    assert "Added category: Coffee" in add.message.replies[0]["text"]
    assert "Renamed category to: Dessert" in rename.message.replies[0]["text"]
    assert "Deleted category: Dessert" in delete.message.replies[0]["text"]

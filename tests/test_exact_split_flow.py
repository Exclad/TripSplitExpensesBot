from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.handlers.expenses import add_expense, exact_amount_message, expense_callback
from tripsplitexpenses.exchange import FixedExchangeRateProvider


def _context(trip_repository, member_repository, expense_repository):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=FixedExchangeRateProvider({}),
    )


def _trip_with_members(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    Alex = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 101)
    return trip, Alex, Sam


async def test_exact_split_prompts_each_selected_member(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    exact_update = fake_callback_update("expense:split:exact", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(exact_update, context)
    assert "How much for" in exact_update.callback_query.message.replies[0]["text"]
    assert _is_force_reply(exact_update.callback_query.message.replies[0]["reply_markup"])

    first = fake_message_update("12.50", user=fake_user(101, "Alex", "Alex"))
    await exact_amount_message(first, context)
    assert "How much for Sam?" in first.message.replies[0]["text"]
    assert _is_force_reply(first.message.replies[0]["reply_markup"])

    second = fake_message_update("12.50", user=fake_user(101, "Alex", "Alex"))
    await exact_amount_message(second, context)
    assert "Ready to save?" in second.message.replies[0]["text"]

    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    expense = expense_repository.list_expenses(trip.id)[0]
    assert expense.split_method == "exact"
    assert sorted(split.amount_minor for split in expense.splits) == [1250, 1250]


async def test_exact_split_mismatch_blocks_save_with_difference(trip_repository, member_repository, expense_repository):
    _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:split:exact", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("12.50", user=fake_user(101, "Alex", "Alex")), context)
    second = fake_message_update("12.49", user=fake_user(101, "Alex", "Alex"))

    await exact_amount_message(second, context)

    assert "Expected 2500 cents, entered 2499 cents, difference 1 cents" in second.message.replies[0]["text"]
    assert second.message.replies[0]["reply_markup"] is not None


async def test_details_callback_shows_exchange_metadata(trip_repository, member_repository, expense_repository):
    trip, _, _ = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    save_update = fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(save_update, context)
    expense = expense_repository.list_expenses(trip.id)[0]
    details_update = fake_callback_update(f"expense:details:{expense.id}", user=fake_user(101, "Alex", "Alex"))

    await expense_callback(details_update, context)

    assert "Rate date:" in details_update.callback_query.message.replies[0]["text"]


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

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


async def test_multiple_payer_flow_prompts_amounts_and_saves(trip_repository, member_repository, expense_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 35.03 dinner", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)

    start = fake_callback_update("expense:payers", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(start, context)
    assert "Who paid?" in start.callback_query.message.replies[0]["text"]
    await expense_callback(fake_callback_update(f"expense:payer-toggle:{Sam.id}", user=fake_user(101, "Alex", "Alex")), context)
    done = fake_callback_update("expense:payers-done", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(done, context)
    assert "How much did Alex pay?" in done.callback_query.message.replies[0]["text"]
    assert _is_force_reply(done.callback_query.message.replies[0]["reply_markup"])

    first = fake_message_update("14.87", user=fake_user(101, "Alex", "Alex"))
    await exact_amount_message(first, context)
    assert "How much did Sam pay?" in first.message.replies[0]["text"]
    assert _is_force_reply(first.message.replies[0]["reply_markup"])
    second = fake_message_update("20.16", user=fake_user(101, "Alex", "Alex"))
    await exact_amount_message(second, context)
    assert "Paid by: Alex + Sam" in second.message.replies[0]["text"]

    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    expense = expense_repository.list_expenses(trip.id)[0]
    assert sorted(payer.amount_minor for payer in expense.payers) == [1487, 2016]


async def test_multiple_payer_mismatch_blocks_confirmation(trip_repository, member_repository, expense_repository):
    _, _, Sam = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 35.03 dinner", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:payers", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:payer-toggle:{Sam.id}", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:payers-done", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("14.87", user=fake_user(101, "Alex", "Alex")), context)
    second = fake_message_update("20.15", user=fake_user(101, "Alex", "Alex"))

    await exact_amount_message(second, context)

    assert "Payer total does not match" in second.message.replies[0]["text"]


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

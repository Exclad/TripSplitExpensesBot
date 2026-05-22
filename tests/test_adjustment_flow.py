from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.handlers.expenses import add_expense, correction_command, exact_amount_message, expense_callback, refund_command
from tripsplitexpenses.exchange import FixedExchangeRateProvider


def _context(trip_repository, member_repository, expense_repository):
    return fake_context(
        trip_repository,
        member_repository,
        expense_repository=expense_repository,
        exchange_rate_provider=FixedExchangeRateProvider({}),
    )


async def _saved_expense(trip_repository, member_repository, expense_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    Alex = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    Sam = member_repository.add_manual_member(trip.id, "Sam", 101)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    return trip, Alex, Sam, context, expense_repository.list_expenses(trip.id)[0]


async def test_refund_creates_linked_labeled_entry(trip_repository, member_repository, expense_repository):
    trip, _, Sam, context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)
    start = fake_message_update("/refund", user=fake_user(101, "Alex", "Alex"))
    await refund_command(start, context)
    assert "Which expense" in start.message.replies[0]["text"]

    await expense_callback(fake_callback_update(f"expense:refund-pick:{expense.id}", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:refund-recipient:{Sam.id}", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("5.00", user=fake_user(101, "Alex", "Alex")), context)

    refund = [item for item in expense_repository.list_expenses(trip.id) if item.entry_type == "refund"][0]
    assert refund.linked_expense_id == expense.id
    assert "Refund" in refund.description
    assert "refunded" in [event.event_type for event in expense_repository.list_audit_events(expense.id)]


async def test_correction_creates_linked_labeled_entry(trip_repository, member_repository, expense_repository):
    trip, _, _, context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)
    start = fake_message_update("/correction", user=fake_user(101, "Alex", "Alex"))
    await correction_command(start, context)
    await expense_callback(fake_callback_update(f"expense:correction-pick:{expense.id}", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("-2.00", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("coupon applied", user=fake_user(101, "Alex", "Alex")), context)

    correction = [item for item in expense_repository.list_expenses(trip.id) if item.entry_type == "correction"][0]
    assert correction.linked_expense_id == expense.id
    assert correction.note == "coupon applied"
    assert "corrected" in [event.event_type for event in expense_repository.list_audit_events(expense.id)]


async def test_original_expense_details_show_refund_and_correction_history(trip_repository, member_repository, expense_repository):
    trip, _, Sam, context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)
    await refund_command(fake_message_update("/refund", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:refund-pick:{expense.id}", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:refund-recipient:{Sam.id}", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("5.00", user=fake_user(101, "Alex", "Alex")), context)
    await correction_command(fake_message_update("/correction", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:correction-pick:{expense.id}", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("-2.00", user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update("coupon applied", user=fake_user(101, "Alex", "Alex")), context)

    details = fake_callback_update(f"expense:details:{expense.id}", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(details, context)

    text = details.callback_query.message.replies[0]["text"]
    assert "History" in text
    assert "Refund recorded" in text
    assert "Correction recorded" in text

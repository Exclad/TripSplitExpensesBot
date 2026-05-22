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


async def _saved_expense(trip_repository, member_repository, expense_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 101)
    member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    member_repository.add_manual_member(trip.id, "Sam", 101)
    context = _context(trip_repository, member_repository, expense_repository)
    await add_expense(fake_message_update("/add 25 lunch", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    return context, expense_repository.list_expenses(trip.id)[0]


async def test_edit_field_picker_updates_description(trip_repository, member_repository, expense_repository):
    context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)

    picker = fake_callback_update(f"expense:edit:{expense.id}", user=fake_user(202, "friend", "Friend"))
    await expense_callback(picker, context)
    assert "What do you want to edit?" in picker.callback_query.message.replies[0]["text"]

    edit_prompt = fake_callback_update(f"expense:edit-field:{expense.id}:description", user=fake_user(202, "friend", "Friend"))
    await expense_callback(edit_prompt, context)
    assert _is_force_reply(edit_prompt.callback_query.message.replies[0]["reply_markup"])
    message = fake_message_update("brunch", user=fake_user(202, "friend", "Friend"))
    await exact_amount_message(message, context)

    assert expense_repository.get_expense(expense.id).description == "brunch"


async def test_details_include_history_with_field_level_edit_and_actor_names(trip_repository, member_repository, expense_repository):
    context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)

    await expense_callback(fake_callback_update(f"expense:edit-field:{expense.id}:description", user=fake_user(202, "friend", "Friend")), context)
    await exact_amount_message(fake_message_update("brunch", user=fake_user(202, "friend", "Friend")), context)
    details = fake_callback_update(f"expense:details:{expense.id}", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(details, context)

    text = details.callback_query.message.replies[0]["text"]
    assert "History" in text
    assert "Alex created" in text
    assert "Friend changed description from lunch to brunch" in text


async def test_delete_requires_confirmation(trip_repository, member_repository, expense_repository):
    context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)

    delete = fake_callback_update(f"expense:delete:{expense.id}", user=fake_user(202, "friend", "Friend"))
    await expense_callback(delete, context)
    assert "Delete this expense?" in delete.callback_query.message.replies[0]["text"]
    assert expense_repository.get_expense(expense.id) is not None

    await expense_callback(fake_callback_update(f"expense:delete-confirm:{expense.id}", user=fake_user(202, "friend", "Friend")), context)
    assert expense_repository.get_expense(expense.id) is None
    assert [event.event_type for event in expense_repository.list_audit_events(expense.id)][-1] == "deleted"


async def test_details_prefer_mapped_member_name_for_audit_actor(trip_repository, member_repository, expense_repository):
    context, expense = await _saved_expense(trip_repository, member_repository, expense_repository)
    trip = trip_repository.get_active_trip(-100)
    Sam = next(member for member in member_repository.list_members(trip.id) if member.display_name == "Sam")
    member_repository.map_manual_member_to_telegram(Sam.id, 202, "sam_real", 101)

    await expense_callback(fake_callback_update(f"expense:edit-field:{expense.id}:note", user=fake_user(202, "sam_real", "Sam Real")), context)
    await exact_amount_message(fake_message_update("paid in cash", user=fake_user(202, "sam_real", "Sam Real")), context)
    details = fake_callback_update(f"expense:details:{expense.id}")
    await expense_callback(details, context)

    text = details.callback_query.message.replies[0]["text"]
    assert "Sam changed note" in text
    assert "Sam Real changed note" not in text


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

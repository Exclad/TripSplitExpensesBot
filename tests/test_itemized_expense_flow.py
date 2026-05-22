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


async def _start_itemized(context):
    await add_expense(fake_message_update("/add 31.01 restaurant", user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update("expense:category:Food", user=fake_user(101, "Alex", "Alex")), context)
    start = fake_callback_update("expense:itemize", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(start, context)
    return start


async def _add_item(context, member_id, name, amount):
    await exact_amount_message(fake_message_update(name, user=fake_user(101, "Alex", "Alex")), context)
    await exact_amount_message(fake_message_update(amount, user=fake_user(101, "Alex", "Alex")), context)
    await expense_callback(fake_callback_update(f"expense:item-member-toggle:{member_id}", user=fake_user(101, "Alex", "Alex")), context)
    done = fake_callback_update("expense:item-members-done", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(done, context)
    return done


async def test_itemized_flow_saves_lines_and_details(trip_repository, member_repository, expense_repository):
    trip, Alex, Sam = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    start = await _start_itemized(context)
    assert "first item" in start.callback_query.message.replies[0]["text"]
    assert _is_force_reply(start.callback_query.message.replies[0]["reply_markup"])

    await _add_item(context, Alex.id, "ramen", "20.00")
    item_add = fake_callback_update("expense:item-add", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(item_add, context)
    assert _is_force_reply(item_add.callback_query.message.replies[0]["reply_markup"])
    await _add_item(context, Sam.id, "tea", "10.00")
    shared = fake_callback_update("expense:item-shared", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(shared, context)
    assert _is_force_reply(shared.callback_query.message.replies[0]["reply_markup"])
    await exact_amount_message(fake_message_update("1.01", user=fake_user(101, "Alex", "Alex")), context)
    confirm = fake_callback_update("expense:item-done", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(confirm, context)

    assert "Items: 2" in confirm.callback_query.message.replies[0]["text"]
    await expense_callback(fake_callback_update("expense:save", user=fake_user(101, "Alex", "Alex")), context)
    expense = expense_repository.list_expenses(trip.id)[0]
    assert expense.split_method == "itemized"
    assert len(expense.line_items) == 2
    assert len(expense.shared_charges) == 1


async def test_itemized_mismatch_blocks_save(trip_repository, member_repository, expense_repository):
    _, Alex, _ = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await _start_itemized(context)
    await _add_item(context, Alex.id, "ramen", "20.00")

    done = fake_callback_update("expense:item-done", user=fake_user(101, "Alex", "Alex"))
    await expense_callback(done, context)

    assert "Itemized total does not match" in done.callback_query.message.replies[0]["text"]


async def test_itemized_flow_offers_exact_split_after_several_items(trip_repository, member_repository, expense_repository):
    _, Alex, _ = _trip_with_members(trip_repository, member_repository)
    context = _context(trip_repository, member_repository, expense_repository)
    await _start_itemized(context)
    for index in range(3):
        if index:
            await expense_callback(fake_callback_update("expense:item-add", user=fake_user(101, "Alex", "Alex")), context)
        last = await _add_item(context, Alex.id, f"item {index}", "1.00")

    buttons = last.callback_query.message.replies[0]["reply_markup"].inline_keyboard
    assert any(row[0].text == "Use exact split instead" for row in buttons)


def _is_force_reply(markup):
    return getattr(markup, "force_reply", False) is True

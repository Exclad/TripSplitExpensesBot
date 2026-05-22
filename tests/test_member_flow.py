from __future__ import annotations

from tests.fakes import fake_callback_update, fake_context, fake_message_update, fake_user
from tripsplitexpenses.bot.copy import (
    JOIN_CALLBACK_DATA,
    JOIN_SUCCESS_MESSAGE,
    MANUAL_ADD_SUCCESS_TEMPLATE,
    MEMBER_MAPPING_CONFIRM_TEMPLATE,
    MEMBER_MAPPING_SUCCESS_TEMPLATE,
    MISSING_TRIP_MESSAGE,
)
from tripsplitexpenses.bot.handlers.members import join_trip_callback, member_callback, members_command
from tripsplitexpenses.bot.handlers.trips import newtrip, trip_status


async def test_join_button_records_clicking_telegram_user(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    update = fake_callback_update(JOIN_CALLBACK_DATA, user=fake_user(101, "Alex", "Alex"))

    await join_trip_callback(update, context)

    trip = trip_repository.get_active_trip(-100)
    members = member_repository.list_members(trip.id)
    assert members[0].display_name == "Alex"
    assert update.callback_query.answers == [JOIN_SUCCESS_MESSAGE]
    assert JOIN_SUCCESS_MESSAGE in update.callback_query.message.replies[0]["text"]


async def test_join_button_requires_active_trip(trip_repository, member_repository):
    update = fake_callback_update(JOIN_CALLBACK_DATA)

    await join_trip_callback(update, fake_context(trip_repository, member_repository))

    assert update.callback_query.answers == ["No active trip yet."]
    assert update.callback_query.message.replies[0]["text"] == MISSING_TRIP_MESSAGE


async def test_members_add_creates_manual_member(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    update = fake_message_update("/members add Sam")

    await members_command(update, context)

    trip = trip_repository.get_active_trip(-100)
    members = member_repository.list_members(trip.id)
    assert [member.display_name for member in members] == ["Sam"]
    assert update.message.replies[0]["text"] == MANUAL_ADD_SUCCESS_TEMPLATE.format(name="Sam")


async def test_trip_summary_shows_joined_and_manual_members(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    await join_trip_callback(fake_callback_update(JOIN_CALLBACK_DATA, user=fake_user(101, "Alex", "Alex")), context)
    await members_command(fake_message_update("/members add Sam"), context)
    update = fake_message_update("/trip")

    await trip_status(update, context)

    assert "Members: 2" in update.message.replies[0]["text"]
    assert "- Alex" in update.message.replies[0]["text"]
    assert "- Sam" in update.message.replies[0]["text"]


async def test_members_claim_lists_unmapped_manual_members_as_buttons(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    await members_command(fake_message_update("/members add Sam"), context)
    update = fake_message_update("/members claim")

    await members_command(update, context)

    reply = update.message.replies[0]
    assert reply["text"] == "Which person are you?"
    assert reply["reply_markup"].inline_keyboard[0][0].text == "Sam"
    assert reply["reply_markup"].inline_keyboard[0][0].callback_data.startswith("members:map-confirm:")


async def test_member_claim_confirmation_links_clicking_user_to_manual_member(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    await members_command(fake_message_update("/members add Sam"), context)
    trip = trip_repository.get_active_trip(-100)
    member = member_repository.list_members(trip.id)[0]
    update = fake_callback_update(f"members:map-confirm:{member.id}", user=fake_user(202, "Sam", "Sam Real"))

    await member_callback(update, context)

    mapped = member_repository.get_member(member.id)
    assert mapped.telegram_user_id == 202
    assert mapped.display_name == "Sam"
    assert update.callback_query.message.replies[0]["text"] == MEMBER_MAPPING_SUCCESS_TEMPLATE.format(name="Sam")


async def test_members_map_prompts_with_existing_expense_warning(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    await members_command(fake_message_update("/members add Sam"), context)
    update = fake_message_update("/members map Sam")

    await members_command(update, context)

    assert update.message.replies[0]["text"] == MEMBER_MAPPING_CONFIRM_TEMPLATE.format(name="Sam")
    buttons = update.message.replies[0]["reply_markup"].inline_keyboard
    assert [button.text for row in buttons for button in row] == ["Link me", "Cancel"]


async def test_trip_summary_keeps_stable_display_name_after_mapping(trip_repository, member_repository):
    context = fake_context(trip_repository, member_repository)
    await newtrip(fake_message_update("/newtrip Demo Trip SGD"), context)
    await members_command(fake_message_update("/members add Sam"), context)
    trip = trip_repository.get_active_trip(-100)
    member = member_repository.list_members(trip.id)[0]
    await member_callback(fake_callback_update(f"members:map-confirm:{member.id}", user=fake_user(202, "sam_real", "Sam Real")), context)
    update = fake_message_update("/trip")

    await trip_status(update, context)

    assert "- Sam" in update.message.replies[0]["text"]
    assert "Sam Real" not in update.message.replies[0]["text"]

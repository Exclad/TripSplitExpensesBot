from __future__ import annotations

from tripsplitexpenses.bot.copy import DUPLICATE_TRIP_MESSAGE, JOIN_SUCCESS_MESSAGE, MANUAL_ADD_SUCCESS_TEMPLATE, MISSING_TRIP_MESSAGE, NEWTRIP_GUIDE_MESSAGE


def test_duplicate_trip_copy_tells_user_what_to_do_next():
    assert "already an active trip" in DUPLICATE_TRIP_MESSAGE
    assert "/trip" in DUPLICATE_TRIP_MESSAGE


def test_join_success_copy_is_plain_language():
    assert "You're in" in JOIN_SUCCESS_MESSAGE
    assert "expenses" in JOIN_SUCCESS_MESSAGE


def test_missing_trip_copy_has_example_command():
    assert "No active trip" in MISSING_TRIP_MESSAGE
    assert "Set up trip" in MISSING_TRIP_MESSAGE


def test_manual_add_copy_uses_member_name():
    assert MANUAL_ADD_SUCCESS_TEMPLATE.format(name="Sam").startswith("Added Sam")


def test_newtrip_guide_has_typable_example():
    assert "/newtrip Korea 2026 SGD KRW" in NEWTRIP_GUIDE_MESSAGE

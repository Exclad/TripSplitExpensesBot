from __future__ import annotations


def test_join_from_telegram_user_creates_member(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    member = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)

    assert member.telegram_user_id == 101
    assert member.username == "Alex"
    assert member.display_name == "Alex"
    assert member.member_type == "telegram"
    assert member.created_by_telegram_id == 101


def test_duplicate_join_is_idempotent(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    first = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    second = member_repository.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)

    assert second.id == first.id
    assert len(member_repository.list_members(trip.id)) == 1


def test_manual_member_can_be_added_without_telegram_username(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    member = member_repository.add_manual_member(trip.id, "Sam", 42)

    assert member.display_name == "Sam"
    assert member.telegram_user_id is None
    assert member.member_type == "manual"


def test_manual_member_can_be_mapped_without_replacing_member_id(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    manual = member_repository.add_manual_member(trip.id, "Sam", 42)

    mapped = member_repository.map_manual_member_to_telegram(manual.id, 202, "Sam", 101)

    assert mapped.id == manual.id
    assert mapped.display_name == "Sam"
    assert mapped.telegram_user_id == 202
    assert mapped.username == "Sam"
    assert mapped.member_type == "telegram"


def test_mapped_member_can_be_found_by_telegram_user_id(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    manual = member_repository.add_manual_member(trip.id, "Sam", 42)
    member_repository.map_manual_member_to_telegram(manual.id, 202, "Sam", 101)

    found = member_repository.find_by_telegram_user_id(trip.id, 202)

    assert found is not None
    assert found.id == manual.id
    assert found.display_name == "Sam"


def test_mapping_rejects_duplicate_telegram_identity(trip_repository, member_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    member_repository.join_from_telegram_user(trip.id, 202, "Sam", "Sam Real", 202)
    manual = member_repository.add_manual_member(trip.id, "Sam", 42)

    try:
        member_repository.map_manual_member_to_telegram(manual.id, 202, "Sam", 101)
    except ValueError as exc:
        assert "already linked" in str(exc)
    else:
        raise AssertionError("Expected duplicate mapping to fail.")

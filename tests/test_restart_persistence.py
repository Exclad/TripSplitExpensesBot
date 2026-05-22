from __future__ import annotations

from tripsplitexpenses.db.connection import connect
from tripsplitexpenses.db.migrations import run_migrations
from tripsplitexpenses.repositories.members import MemberRepository
from tripsplitexpenses.repositories.trips import TripRepository


def test_trip_and_member_survive_reopened_connection(tmp_path):
    database_path = tmp_path / "restart.sqlite3"
    first = connect(database_path)
    run_migrations(first)
    trip_repo = TripRepository(first)
    member_repo = MemberRepository(first)
    trip = trip_repo.create_trip(-100, "Demo Trip", "SGD", 42)
    member_repo.join_from_telegram_user(trip.id, 101, "Alex", "Alex", 101)
    first.close()

    second = connect(database_path)
    run_migrations(second)
    try:
        reopened_trip_repo = TripRepository(second)
        reopened_member_repo = MemberRepository(second)
        reopened_trip = reopened_trip_repo.get_active_trip(-100)

        assert reopened_trip is not None
        assert reopened_trip.name == "Demo Trip"
        assert [member.display_name for member in reopened_member_repo.list_members(reopened_trip.id)] == ["Alex"]
    finally:
        second.close()

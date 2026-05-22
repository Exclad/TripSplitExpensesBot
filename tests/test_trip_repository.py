from __future__ import annotations

import pytest

from tripsplitexpenses.repositories.trips import ActiveTripExistsError


def test_repository_can_create_and_fetch_active_trip_by_chat_id(trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "sgd", 42)

    fetched = trip_repository.get_active_trip(-100)

    assert fetched == trip
    assert fetched is not None
    assert fetched.base_currency == "SGD"
    assert fetched.created_by_telegram_id == 42
    assert fetched.created_at
    assert fetched.updated_at


def test_second_active_trip_in_same_chat_is_rejected(trip_repository):
    trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    with pytest.raises(ActiveTripExistsError):
        trip_repository.create_trip(-100, "Korea 2025", "SGD", 42)


def test_archived_trip_allows_new_active_trip(trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    trip_repository.archive_trip(trip.id, archived_by_telegram_id=42)
    next_trip = trip_repository.create_trip(-100, "Korea 2025", "SGD", 42)

    assert next_trip.name == "Korea 2025"


def test_archive_trip_returns_archived_trip_metadata(trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)

    archived = trip_repository.archive_trip(trip.id, archived_by_telegram_id=99)

    assert archived.status == "archived"
    assert archived.archived_at
    assert archived.archived_by_telegram_id == 99
    assert trip_repository.get_active_trip(-100) is None


def test_reopen_trip_restores_archived_trip(trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=99)

    reopened = trip_repository.reopen_trip(trip.id, reopened_by_telegram_id=101)

    assert reopened.status == "active"
    assert reopened.archived_at is None
    assert reopened.archived_by_telegram_id is None
    assert trip_repository.get_active_trip(-100) == reopened


def test_reopen_trip_rejects_conflicting_active_trip(trip_repository):
    trip = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    trip_repository.archive_trip(trip.id, archived_by_telegram_id=99)
    trip_repository.create_trip(-100, "Korea 2025", "SGD", 42)

    with pytest.raises(ActiveTripExistsError):
        trip_repository.reopen_trip(trip.id, reopened_by_telegram_id=101)


def test_readable_trip_returns_active_then_latest_archived(trip_repository):
    first = trip_repository.create_trip(-100, "Demo Trip", "SGD", 42)
    trip_repository.archive_trip(first.id, archived_by_telegram_id=99)

    assert trip_repository.get_readable_trip(-100) == trip_repository.get_trip(first.id)

    active = trip_repository.create_trip(-100, "Korea 2025", "SGD", 42)

    assert trip_repository.get_readable_trip(-100) == active

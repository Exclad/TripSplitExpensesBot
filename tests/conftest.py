from __future__ import annotations

import pytest

from tripsplitexpenses.db.connection import connect
from tripsplitexpenses.db.migrations import run_migrations
from tripsplitexpenses.repositories.members import MemberRepository
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.repositories.trips import TripRepository


@pytest.fixture
def connection(tmp_path):
    db = connect(tmp_path / "test.sqlite3")
    run_migrations(db)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def trip_repository(connection):
    return TripRepository(connection)


@pytest.fixture
def member_repository(connection):
    return MemberRepository(connection)


@pytest.fixture
def expense_repository(connection):
    return ExpenseRepository(connection)

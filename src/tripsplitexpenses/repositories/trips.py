from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


class ActiveTripExistsError(ValueError):
    pass


class TripNotFoundError(ValueError):
    pass


class TripIsArchivedError(ValueError):
    pass


@dataclass(frozen=True)
class Trip:
    id: str
    telegram_chat_id: int
    name: str
    base_currency: str
    default_expense_currency: str
    status: str
    created_at: str
    updated_at: str
    created_by_telegram_id: int
    archived_at: str | None = None
    archived_by_telegram_id: int | None = None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _trip_from_row(row: sqlite3.Row | None) -> Trip | None:
    if row is None:
        return None
    return Trip(
        id=row["id"],
        telegram_chat_id=row["telegram_chat_id"],
        name=row["name"],
        base_currency=row["base_currency"],
        default_expense_currency=row["default_expense_currency"] or row["base_currency"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_telegram_id=row["created_by_telegram_id"],
        archived_at=row["archived_at"],
        archived_by_telegram_id=row["archived_by_telegram_id"],
    )


class TripRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_trip(
        self,
        telegram_chat_id: int,
        name: str,
        base_currency: str,
        created_by_telegram_id: int,
        default_expense_currency: str | None = None,
    ) -> Trip:
        timestamp = _now()
        base_code = _normalize_currency(base_currency)
        default_code = _normalize_currency(default_expense_currency or base_code)
        trip = Trip(
            id=str(uuid.uuid4()),
            telegram_chat_id=telegram_chat_id,
            name=name.strip(),
            base_currency=base_code,
            default_expense_currency=default_code,
            status="active",
            created_at=timestamp,
            updated_at=timestamp,
            created_by_telegram_id=created_by_telegram_id,
        )
        try:
            self.connection.execute(
                """
                INSERT INTO trips (
                    id, telegram_chat_id, name, base_currency, default_expense_currency, status,
                    created_at, updated_at, created_by_telegram_id,
                    archived_at, archived_by_telegram_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trip.id,
                    trip.telegram_chat_id,
                    trip.name,
                    trip.base_currency,
                    trip.default_expense_currency,
                    trip.status,
                    trip.created_at,
                    trip.updated_at,
                    trip.created_by_telegram_id,
                    trip.archived_at,
                    trip.archived_by_telegram_id,
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ActiveTripExistsError("This chat already has an active trip.") from exc
        return trip

    def get_active_trip(self, telegram_chat_id: int) -> Trip | None:
        row = self.connection.execute(
            "SELECT * FROM trips WHERE telegram_chat_id = ? AND status = 'active'",
            (telegram_chat_id,),
        ).fetchone()
        return _trip_from_row(row)

    def get_readable_trip(self, telegram_chat_id: int) -> Trip | None:
        active = self.get_active_trip(telegram_chat_id)
        if active is not None:
            return active
        row = self.connection.execute(
            """
            SELECT * FROM trips
            WHERE telegram_chat_id = ? AND status = 'archived'
            ORDER BY archived_at DESC, updated_at DESC
            LIMIT 1
            """,
            (telegram_chat_id,),
        ).fetchone()
        return _trip_from_row(row)

    def get_trip(self, trip_id: str) -> Trip | None:
        row = self.connection.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        return _trip_from_row(row)

    def archive_trip(self, trip_id: str, archived_by_telegram_id: int) -> Trip:
        timestamp = _now()
        cursor = self.connection.execute(
            """
            UPDATE trips
            SET status = 'archived',
                archived_at = ?,
                archived_by_telegram_id = ?,
                updated_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (timestamp, archived_by_telegram_id, timestamp, trip_id),
        )
        self.connection.commit()
        if cursor.rowcount == 0:
            trip = self.get_trip(trip_id)
            if trip is None:
                raise TripNotFoundError("Trip not found.")
            raise TripIsArchivedError("This trip is already archived.")
        archived = self.get_trip(trip_id)
        if archived is None:
            raise TripNotFoundError("Trip not found.")
        return archived

    def reopen_trip(self, trip_id: str, reopened_by_telegram_id: int) -> Trip:
        trip = self.get_trip(trip_id)
        if trip is None:
            raise TripNotFoundError("Trip not found.")
        if trip.status == "active":
            return trip
        existing_active = self.get_active_trip(trip.telegram_chat_id)
        if existing_active is not None and existing_active.id != trip_id:
            raise ActiveTripExistsError("This chat already has an active trip.")

        timestamp = _now()
        self.connection.execute(
            """
            UPDATE trips
            SET status = 'active',
                archived_at = NULL,
                archived_by_telegram_id = NULL,
                updated_at = ?
            WHERE id = ? AND status = 'archived'
            """,
            (timestamp, trip_id),
        )
        self.connection.commit()
        reopened = self.get_trip(trip_id)
        if reopened is None:
            raise TripNotFoundError("Trip not found.")
        return reopened


def _normalize_currency(currency: str) -> str:
    code = currency.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("Use a 3-letter currency code like SGD or KRW.")
    return code

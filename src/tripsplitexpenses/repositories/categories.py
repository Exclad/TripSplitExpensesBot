from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from tripsplitexpenses.categories import BUILT_IN_CATEGORIES, category_key, validate_custom_category_name


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class TripCategory:
    id: str
    trip_id: str
    name: str
    normalized_name: str
    created_at: str
    updated_at: str
    created_by_telegram_id: int
    deleted_at: str | None = None
    deleted_by_telegram_id: int | None = None


def _category_from_row(row: sqlite3.Row) -> TripCategory:
    return TripCategory(
        id=row["id"],
        trip_id=row["trip_id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_telegram_id=row["created_by_telegram_id"],
        deleted_at=row["deleted_at"],
        deleted_by_telegram_id=row["deleted_by_telegram_id"],
    )


class CategoryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_category(self, trip_id: str, name: str, created_by_telegram_id: int) -> TripCategory:
        clean = validate_custom_category_name(name)
        normalized = category_key(clean)
        if normalized in {category_key(category) for category in BUILT_IN_CATEGORIES}:
            raise ValueError("That category already exists.")
        existing = self.connection.execute(
            """
            SELECT 1 FROM trip_categories
            WHERE trip_id = ? AND normalized_name = ? AND deleted_at IS NULL
            """,
            (trip_id, normalized),
        ).fetchone()
        if existing:
            raise ValueError("That category already exists.")
        timestamp = _now()
        category = TripCategory(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            name=clean,
            normalized_name=normalized,
            created_at=timestamp,
            updated_at=timestamp,
            created_by_telegram_id=created_by_telegram_id,
        )
        self.connection.execute(
            """
            INSERT INTO trip_categories (
                id, trip_id, name, normalized_name, created_at, updated_at,
                created_by_telegram_id, deleted_at, deleted_by_telegram_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category.id,
                category.trip_id,
                category.name,
                category.normalized_name,
                category.created_at,
                category.updated_at,
                category.created_by_telegram_id,
                category.deleted_at,
                category.deleted_by_telegram_id,
            ),
        )
        self.connection.commit()
        return category

    def list_custom_categories(self, trip_id: str) -> list[TripCategory]:
        rows = self.connection.execute(
            """
            SELECT * FROM trip_categories
            WHERE trip_id = ? AND deleted_at IS NULL
            ORDER BY lower(name), created_at
            """,
            (trip_id,),
        ).fetchall()
        return [_category_from_row(row) for row in rows]

    def list_category_names(self, trip_id: str) -> list[str]:
        return list(BUILT_IN_CATEGORIES) + [category.name for category in self.list_custom_categories(trip_id)]

    def rename_category(self, category_id: str, new_name: str) -> TripCategory:
        clean = validate_custom_category_name(new_name)
        normalized = category_key(clean)
        current = self.connection.execute(
            "SELECT * FROM trip_categories WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        ).fetchone()
        if current is None:
            raise ValueError("Category not found.")
        duplicate = self.connection.execute(
            """
            SELECT 1 FROM trip_categories
            WHERE trip_id = ? AND normalized_name = ? AND id <> ? AND deleted_at IS NULL
            """,
            (current["trip_id"], normalized, category_id),
        ).fetchone()
        if duplicate:
            raise ValueError("That category already exists.")
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE trip_categories
            SET name = ?, normalized_name = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (clean, normalized, timestamp, category_id),
        )
        self.connection.execute(
            """
            UPDATE expenses
            SET category = ?, updated_at = ?
            WHERE trip_id = ? AND category = ? AND deleted_at IS NULL
            """,
            (clean, timestamp, current["trip_id"], current["name"]),
        )
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM trip_categories WHERE id = ?", (category_id,)).fetchone()
        return _category_from_row(row)

    def delete_category(self, category_id: str, deleted_by_telegram_id: int) -> None:
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE trip_categories
            SET deleted_at = ?, deleted_by_telegram_id = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (timestamp, deleted_by_telegram_id, timestamp, category_id),
        )
        self.connection.commit()

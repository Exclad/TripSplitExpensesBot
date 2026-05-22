from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Member:
    id: str
    trip_id: str
    telegram_user_id: int | None
    username: str | None
    display_name: str
    member_type: str
    created_at: str
    updated_at: str
    created_by_telegram_id: int
    deleted_at: str | None = None
    deleted_by_telegram_id: int | None = None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _member_from_row(row: sqlite3.Row | None) -> Member | None:
    if row is None:
        return None
    return Member(
        id=row["id"],
        trip_id=row["trip_id"],
        telegram_user_id=row["telegram_user_id"],
        username=row["username"],
        display_name=row["display_name"],
        member_type=row["member_type"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_telegram_id=row["created_by_telegram_id"],
        deleted_at=row["deleted_at"],
        deleted_by_telegram_id=row["deleted_by_telegram_id"],
    )


class MemberRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def join_from_telegram_user(
        self,
        trip_id: str,
        telegram_user_id: int,
        username: str | None,
        display_name: str,
        created_by_telegram_id: int,
    ) -> Member:
        existing = self.connection.execute(
            """
            SELECT * FROM members
            WHERE trip_id = ? AND telegram_user_id = ? AND deleted_at IS NULL
            """,
            (trip_id, telegram_user_id),
        ).fetchone()
        if existing:
            return _member_from_row(existing)  # type: ignore[return-value]

        return self._insert_member(
            trip_id=trip_id,
            telegram_user_id=telegram_user_id,
            username=username,
            display_name=display_name,
            member_type="telegram",
            created_by_telegram_id=created_by_telegram_id,
        )

    def add_manual_member(self, trip_id: str, display_name: str, created_by_telegram_id: int) -> Member:
        return self._insert_member(
            trip_id=trip_id,
            telegram_user_id=None,
            username=None,
            display_name=display_name,
            member_type="manual",
            created_by_telegram_id=created_by_telegram_id,
        )

    def list_members(self, trip_id: str) -> list[Member]:
        rows = self.connection.execute(
            """
            SELECT * FROM members
            WHERE trip_id = ? AND deleted_at IS NULL
            ORDER BY lower(display_name), created_at
            """,
            (trip_id,),
        ).fetchall()
        return [member for row in rows if (member := _member_from_row(row)) is not None]

    def list_unmapped_manual_members(self, trip_id: str) -> list[Member]:
        rows = self.connection.execute(
            """
            SELECT * FROM members
            WHERE trip_id = ?
              AND member_type = 'manual'
              AND telegram_user_id IS NULL
              AND deleted_at IS NULL
            ORDER BY lower(display_name), created_at
            """,
            (trip_id,),
        ).fetchall()
        return [member for row in rows if (member := _member_from_row(row)) is not None]

    def get_member(self, member_id: str) -> Member | None:
        row = self.connection.execute(
            "SELECT * FROM members WHERE id = ? AND deleted_at IS NULL",
            (member_id,),
        ).fetchone()
        return _member_from_row(row)

    def find_by_telegram_user_id(self, trip_id: str, telegram_user_id: int) -> Member | None:
        row = self.connection.execute(
            """
            SELECT * FROM members
            WHERE trip_id = ? AND telegram_user_id = ? AND deleted_at IS NULL
            """,
            (trip_id, telegram_user_id),
        ).fetchone()
        return _member_from_row(row)

    def find_by_display_name(self, trip_id: str, display_name: str) -> Member | None:
        row = self.connection.execute(
            """
            SELECT * FROM members
            WHERE trip_id = ? AND lower(display_name) = lower(?) AND deleted_at IS NULL
            ORDER BY created_at
            LIMIT 1
            """,
            (trip_id, display_name.strip()),
        ).fetchone()
        return _member_from_row(row)

    def map_manual_member_to_telegram(
        self,
        member_id: str,
        telegram_user_id: int,
        username: str | None,
        mapped_by_telegram_id: int,
    ) -> Member:
        member = self.get_member(member_id)
        if member is None:
            raise ValueError("Member not found.")
        if member.member_type != "manual" or member.telegram_user_id is not None:
            raise ValueError("That member is already linked to Telegram.")
        duplicate = self.find_by_telegram_user_id(member.trip_id, telegram_user_id)
        if duplicate is not None and duplicate.id != member.id:
            raise ValueError("That Telegram user is already linked to another trip member.")
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE members
            SET telegram_user_id = ?,
                username = ?,
                member_type = 'telegram',
                updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (telegram_user_id, username, timestamp, member_id),
        )
        self.connection.commit()
        mapped = self.get_member(member_id)
        if mapped is None:
            raise ValueError("Member not found.")
        return mapped

    def remove_member(self, member_id: str, deleted_by_telegram_id: int) -> None:
        timestamp = _now()
        self.connection.execute(
            """
            UPDATE members
            SET deleted_at = ?, deleted_by_telegram_id = ?, updated_at = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (timestamp, deleted_by_telegram_id, timestamp, member_id),
        )
        self.connection.commit()

    def _insert_member(
        self,
        trip_id: str,
        telegram_user_id: int | None,
        username: str | None,
        display_name: str,
        member_type: str,
        created_by_telegram_id: int,
    ) -> Member:
        timestamp = _now()
        member = Member(
            id=str(uuid.uuid4()),
            trip_id=trip_id,
            telegram_user_id=telegram_user_id,
            username=username,
            display_name=display_name.strip(),
            member_type=member_type,
            created_at=timestamp,
            updated_at=timestamp,
            created_by_telegram_id=created_by_telegram_id,
        )
        self.connection.execute(
            """
            INSERT INTO members (
                id, trip_id, telegram_user_id, username, display_name,
                member_type, created_at, updated_at, created_by_telegram_id,
                deleted_at, deleted_by_telegram_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                member.id,
                member.trip_id,
                member.telegram_user_id,
                member.username,
                member.display_name,
                member.member_type,
                member.created_at,
                member.updated_at,
                member.created_by_telegram_id,
                member.deleted_at,
                member.deleted_by_telegram_id,
            ),
        )
        self.connection.commit()
        return member

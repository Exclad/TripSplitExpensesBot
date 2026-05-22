from __future__ import annotations

import sqlite3


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _has_column(connection, table, column):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def run_migrations(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            telegram_chat_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            base_currency TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_telegram_id INTEGER NOT NULL,
            archived_at TEXT,
            archived_by_telegram_id INTEGER
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_trips_one_active_per_chat
            ON trips(telegram_chat_id)
            WHERE status = 'active';

        CREATE TABLE IF NOT EXISTS members (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            telegram_user_id INTEGER,
            username TEXT,
            display_name TEXT NOT NULL,
            member_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_telegram_id INTEGER NOT NULL,
            deleted_at TEXT,
            deleted_by_telegram_id INTEGER
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_members_one_telegram_user_per_trip
            ON members(trip_id, telegram_user_id)
            WHERE telegram_user_id IS NOT NULL AND deleted_at IS NULL;

        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            split_method TEXT NOT NULL,
            original_amount_minor INTEGER NOT NULL,
            original_currency TEXT NOT NULL,
            base_amount_minor INTEGER NOT NULL,
            base_currency TEXT NOT NULL,
            exchange_rate TEXT NOT NULL,
            exchange_rate_date TEXT NOT NULL,
            exchange_rate_provider TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_telegram_id INTEGER NOT NULL,
            deleted_at TEXT,
            deleted_by_telegram_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS expense_payers (
            id TEXT PRIMARY KEY,
            expense_id TEXT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            member_id TEXT NOT NULL REFERENCES members(id),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expense_splits (
            id TEXT PRIMARY KEY,
            expense_id TEXT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            member_id TEXT NOT NULL REFERENCES members(id),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expense_line_items (
            id TEXT PRIMARY KEY,
            expense_id TEXT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            original_amount_minor INTEGER NOT NULL,
            base_amount_minor INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expense_line_item_shares (
            id TEXT PRIMARY KEY,
            line_item_id TEXT NOT NULL REFERENCES expense_line_items(id) ON DELETE CASCADE,
            member_id TEXT NOT NULL REFERENCES members(id),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expense_shared_charges (
            id TEXT PRIMARY KEY,
            expense_id TEXT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            original_amount_minor INTEGER NOT NULL,
            base_amount_minor INTEGER NOT NULL,
            allocation_method TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trip_categories (
            id TEXT PRIMARY KEY,
            trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by_telegram_id INTEGER NOT NULL,
            deleted_at TEXT,
            deleted_by_telegram_id INTEGER
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_trip_categories_active_name
            ON trip_categories(trip_id, normalized_name)
            WHERE deleted_at IS NULL;

        CREATE TABLE IF NOT EXISTS expense_audit_events (
            id TEXT PRIMARY KEY,
            expense_id TEXT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            linked_expense_id TEXT,
            actor_telegram_id INTEGER,
            actor_display_name TEXT,
            field_name TEXT,
            old_value TEXT,
            new_value TEXT,
            summary TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    _add_column(connection, "expenses", "entry_type", "TEXT NOT NULL DEFAULT 'expense'")
    _add_column(connection, "expenses", "linked_expense_id", "TEXT")
    _add_column(connection, "expenses", "note", "TEXT")
    _add_column(connection, "trips", "default_expense_currency", "TEXT")
    connection.execute("UPDATE trips SET default_expense_currency = base_currency WHERE default_expense_currency IS NULL")
    connection.commit()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class SettingsError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    data_dir: Path
    database_path: Path
    owner_telegram_id: int | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SettingsError("TELEGRAM_BOT_TOKEN is required to start the bot.")
        owner_raw = source.get("OWNER_TELEGRAM_ID", "").strip()
        owner_telegram_id: int | None = None
        if owner_raw:
            try:
                owner_telegram_id = int(owner_raw)
            except ValueError as exc:
                raise SettingsError("OWNER_TELEGRAM_ID must be a Telegram numeric user ID.") from exc

        database_override = source.get("DATABASE_PATH")
        data_dir = Path(source.get("DATA_DIR") or source.get("TRIPSPLIT_DATA_DIR") or "/data")
        database_path = Path(database_override) if database_override else data_dir / "tripsplitexpenses.sqlite3"
        if database_override and "DATA_DIR" not in source and "TRIPSPLIT_DATA_DIR" not in source:
            data_dir = database_path.parent
        data_dir.mkdir(parents=True, exist_ok=True)
        database_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            telegram_bot_token=token,
            data_dir=data_dir,
            database_path=database_path,
            owner_telegram_id=owner_telegram_id,
        )

from __future__ import annotations

import pytest

from tripsplitexpenses.settings import Settings, SettingsError


def test_settings_default_to_data_dir_database_path(tmp_path):
    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": "token", "DATA_DIR": str(tmp_path), "OWNER_TELEGRAM_ID": "12345"})

    assert settings.data_dir == tmp_path
    assert settings.database_path == tmp_path / "tripsplitexpenses.sqlite3"
    assert settings.owner_telegram_id == 12345
    assert settings.data_dir.exists()


def test_settings_allow_database_path_override(tmp_path):
    database_path = tmp_path / "nested" / "bot.sqlite3"

    settings = Settings.from_env({"TELEGRAM_BOT_TOKEN": "token", "DATABASE_PATH": str(database_path)})

    assert settings.database_path == database_path
    assert database_path.parent.exists()


def test_missing_token_fails_fast_without_revealing_secret(tmp_path):
    with pytest.raises(SettingsError, match="TELEGRAM_BOT_TOKEN is required"):
        Settings.from_env({"DATA_DIR": str(tmp_path)})


def test_invalid_owner_telegram_id_fails_fast(tmp_path):
    with pytest.raises(SettingsError, match="OWNER_TELEGRAM_ID must be a Telegram numeric user ID"):
        Settings.from_env({"TELEGRAM_BOT_TOKEN": "token", "OWNER_TELEGRAM_ID": "not-a-number", "DATA_DIR": str(tmp_path)})

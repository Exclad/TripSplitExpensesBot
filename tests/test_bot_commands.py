from __future__ import annotations

from tripsplitexpenses.bot.commands import BOT_COMMANDS


def test_bot_command_menu_includes_core_navigation_commands():
    command_names = [command for command, _ in BOT_COMMANDS]

    assert command_names[:3] == ["start", "menu", "add"]
    assert "balance" in command_names
    assert "trip" in command_names
    assert "members" in command_names
    assert "help" in command_names

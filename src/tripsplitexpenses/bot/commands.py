from __future__ import annotations

from typing import Any


BOT_COMMANDS = [
    ("start", "Show the main buttons"),
    ("menu", "Show the main buttons"),
    ("add", "Add an expense"),
    ("balance", "Show balances"),
    ("trip", "Show trip status"),
    ("members", "Show or manage members"),
    ("newtrip", "Set up a new trip"),
    ("archive", "Archive the active trip"),
    ("reopen", "Reopen the archived trip"),
    ("help", "Show help"),
]


async def configure_bot_commands(application: Any) -> None:
    from telegram import BotCommand, MenuButtonCommands

    await application.bot.set_my_commands([BotCommand(command, description) for command, description in BOT_COMMANDS])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

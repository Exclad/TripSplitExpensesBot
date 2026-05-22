from __future__ import annotations

from tripsplitexpenses.bot.copy import JOIN_CALLBACK_DATA
from tripsplitexpenses.bot.auth import owner_gate
from tripsplitexpenses.bot.commands import configure_bot_commands
from tripsplitexpenses.bot.handlers.balances import balance_callback, balance_command
from tripsplitexpenses.bot.handlers.categories import categories_command
from tripsplitexpenses.bot.handlers.expenses import add_expense, correction_command, exact_amount_message, expense_callback, refund_command
from tripsplitexpenses.bot.handlers.help import help_callback, help_command
from tripsplitexpenses.bot.handlers.members import join_trip_callback, member_callback, members_command
from tripsplitexpenses.bot.handlers.navigation import menu_command, text_router
from tripsplitexpenses.bot.handlers.trips import archive_command, newtrip, reopen_command, trip_callback, trip_status
from tripsplitexpenses.db.connection import connect
from tripsplitexpenses.db.migrations import run_migrations
from tripsplitexpenses.repositories.members import MemberRepository
from tripsplitexpenses.repositories.categories import CategoryRepository
from tripsplitexpenses.repositories.expenses import ExpenseRepository
from tripsplitexpenses.repositories.trips import TripRepository
from tripsplitexpenses.settings import Settings


def build_application(settings: Settings):
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler, filters

    connection = connect(settings.database_path)
    run_migrations(connection)

    application = Application.builder().token(settings.telegram_bot_token).post_init(configure_bot_commands).build()
    application.bot_data["connection"] = connection
    application.bot_data["trip_repository"] = TripRepository(connection)
    application.bot_data["member_repository"] = MemberRepository(connection)
    application.bot_data["expense_repository"] = ExpenseRepository(connection)
    application.bot_data["category_repository"] = CategoryRepository(connection)
    application.bot_data["owner_telegram_id"] = settings.owner_telegram_id

    application.add_handler(TypeHandler(Update, owner_gate), group=-1)
    application.add_handler(CommandHandler("start", menu_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("newtrip", newtrip))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("trip", trip_status))
    application.add_handler(CommandHandler("archive", archive_command))
    application.add_handler(CommandHandler("reopen", reopen_command))
    application.add_handler(CommandHandler("members", members_command))
    application.add_handler(CommandHandler("add", add_expense))
    application.add_handler(CommandHandler("refund", refund_command))
    application.add_handler(CommandHandler("correction", correction_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(join_trip_callback, pattern=f"^{JOIN_CALLBACK_DATA}$"))
    application.add_handler(CallbackQueryHandler(member_callback, pattern=r"^members:"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern=r"^help:"))
    application.add_handler(CallbackQueryHandler(trip_callback, pattern=r"^trip:(archive|reopen|setup):"))
    application.add_handler(CallbackQueryHandler(balance_callback, pattern=r"^balance:"))
    application.add_handler(CallbackQueryHandler(expense_callback, pattern=r"^expense:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    return application


def run() -> None:
    settings = Settings.from_env()
    application = build_application(settings)
    application.run_polling()

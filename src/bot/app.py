"""Telegram bot application setup and entry point."""

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from .handlers import (
    apply_command,
    handle_callback,
    handle_url_message,
    help_command,
    profile_command,
    referrals_command,
    scheduled_scout,
    scout_command,
    search_command,
    start_command,
)
from ..profile_loader import load_settings

logger = logging.getLogger(__name__)


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    load_dotenv()

    # Try to get token from env first, then from settings.yaml
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        settings = load_settings()
        token = settings.get("telegram", {}).get("merinaukri")

    if not token:
        raise ValueError(
            "Telegram bot token not found. Set TELEGRAM_BOT_TOKEN in .env "
            "or merinaukri in config/settings.yaml"
        )

    # Increase timeouts for file uploads (default 5s is too short)
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=60.0,
        write_timeout=60.0,
    )
    app = Application.builder().token(token).request(request).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("apply", apply_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("referrals", referrals_command))
    app.add_handler(CommandHandler("scout", scout_command))

    # Callback handler for inline keyboard buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Message handler for plain URLs (catch-all)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))

    # Schedule automatic job scouting
    settings = load_settings()
    scout_interval = settings.get("scout", {}).get("interval_hours", 6)
    interval_seconds = scout_interval * 3600
    app.job_queue.run_repeating(
        scheduled_scout,
        interval=interval_seconds,
        first=60,  # first run 60s after bot starts
        name="scheduled_scout",
    )
    logger.info(f"Scheduled job scout every {scout_interval} hours")

    return app


async def _set_commands(app: Application):
    """Register bot commands so they appear in the Telegram / menu."""
    await app.bot.set_my_commands([
        BotCommand("start", "Welcome & save your chat ID"),
        BotCommand("scout", "Find new matching jobs NOW"),
        BotCommand("apply", "Generate resume & cover letter for a job URL"),
        BotCommand("search", "Search job boards — /search <query>"),
        BotCommand("referrals", "Find LinkedIn connections — /referrals <company>"),
        BotCommand("profile", "Show your profile summary"),
        BotCommand("help", "Show all commands"),
    ])
    logger.info("Bot commands registered in Telegram menu")


def run_bot():
    """Start the Telegram bot."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    logger.info("Starting Job Application Assistant bot...")
    app = create_bot()
    app.post_init = _set_commands
    app.run_polling(drop_pending_updates=True)
    logger.info("Bot stopped.")

"""
bot.py – aiogram 3.x Telegram bot handlers and entry point.

Commands
────────
/start   – Greet the user and confirm the watcher is active.
/status  – Show runtime statistics (events checked, signals sent, last poll).
/help    – Display available commands.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, BotCommand

import config
from config import configure_logging
from formatter import format_startup_message, format_status_message
from watcher import CalendarWatcher

# ── Logging ───────────────────────────────────────────────────────────────────
configure_logging()
logger = logging.getLogger(__name__)

# ── Bot & Dispatcher ──────────────────────────────────────────────────────────
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# The watcher is a module-level singleton so handlers can reference it
watcher: CalendarWatcher | None = None


# ── Command handlers ──────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Greet the user and confirm the monitoring loop is active."""
    text = format_startup_message(config.POLL_INTERVAL_SECONDS)
    await message.answer(text, parse_mode="MarkdownV2")


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Return current watcher statistics."""
    if watcher is None:
        await message.answer("⚠️ Watcher is not yet initialised\\.", parse_mode="MarkdownV2")
        return

    text = format_status_message(
        checked_events=watcher.events_checked,
        signals_sent=watcher.signals_sent,
        last_check=watcher.last_check,
    )
    await message.answer(text, parse_mode="MarkdownV2")


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """List available commands."""
    help_text = (
        "🤖 *XAUT/USDT Signal Bot — Команды*\n\n"
        "/start — Запустить и подтвердить активность бота\n"
        "/status — Статистика: проверено событий, отправлено сигналов\n"
        "/help — Показать это сообщение"
    )
    await message.answer(help_text, parse_mode="MarkdownV2")


# ── Bot menu registration ─────────────────────────────────────────────────────

async def _set_bot_commands() -> None:
    commands = [
        BotCommand(command="start",  description="Запустить бот / подтвердить активность"),
        BotCommand(command="status", description="Статистика мониторинга"),
        BotCommand(command="help",   description="Список команд"),
    ]
    await bot.set_my_commands(commands)


# ── Startup / Shutdown hooks ──────────────────────────────────────────────────

async def on_startup() -> None:
    global watcher

    logger.info("Bot starting up…")
    await _set_bot_commands()

    # Create and start the background calendar watcher
    watcher = CalendarWatcher(
        bot=bot,
        admin_chat_id=config.ADMIN_CHAT_ID,
        poll_interval=config.POLL_INTERVAL_SECONDS,
    )
    watcher.start()

    # Send startup notification to the admin chat
    try:
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=format_startup_message(config.POLL_INTERVAL_SECONDS),
            parse_mode="MarkdownV2",
        )
    except Exception as exc:
        logger.error("Could not send startup message: %s", exc)

    logger.info(
        "Bot is up — polling every %d s — admin chat: %s",
        config.POLL_INTERVAL_SECONDS,
        config.ADMIN_CHAT_ID,
    )


async def on_shutdown() -> None:
    logger.info("Bot shutting down…")
    if watcher:
        watcher.stop()
    await bot.session.close()


# ── Main entry point ──────────────────────────────────────────────────────────

async def main() -> None:
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting aiogram polling loop…")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

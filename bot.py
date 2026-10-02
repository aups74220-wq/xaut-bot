"""
bot.py – aiogram 3.x Telegram bot handlers and entry point.

Commands
────────
/start   – Greet the user, confirm watcher is active, and show past & next news.
/news    – Show Message 1 (past news) and Message 2 (next upcoming news) in Yerevan time.
/status  – Show runtime statistics (events checked, signals sent, last poll).
/help    – Display available commands.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BotCommand, Message

import config
from config import configure_logging
from formatter import (
    format_next_event_message,
    format_past_event_message,
    format_startup_message,
    format_status_message,
)
from parser import get_past_and_next_events
from watcher import CalendarWatcher

# ── Logging ───────────────────────────────────────────────────────────────────
configure_logging()
logger = logging.getLogger(__name__)

# ── Bot & Dispatcher ──────────────────────────────────────────────────────────
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# The watcher is a module-level singleton so handlers can reference it
watcher: CalendarWatcher | None = None


async def _send_news_messages(target_bot: Bot, chat_id: int | str) -> None:
    """
    Fetch and send:
    - Message 1: Most recent past news (with Yerevan time, impact, actual, forecast, reaction).
    - Message 2: Next upcoming news (with Yerevan time, countdown, forecast, XAUT expectation).
    """
    loop = asyncio.get_event_loop()
    try:
        past_event, next_event = await loop.run_in_executor(None, get_past_and_next_events)
    except Exception as exc:
        logger.error("Error retrieving past/next events: %s", exc)
        await target_bot.send_message(
            chat_id=chat_id,
            text="⚠️ Не удалось загрузить экономический календарь\\. Попробуйте позже\\.",
            parse_mode="MarkdownV2",
        )
        return

    # Message 1: Past news
    if past_event:
        msg_past = format_past_event_message(past_event)
        await target_bot.send_message(chat_id=chat_id, text=msg_past, parse_mode="MarkdownV2")
    else:
        await target_bot.send_message(
            chat_id=chat_id,
            text="ℹ️ _Данные о прошлых важных новостях за эту неделю не найдены\\._",
            parse_mode="MarkdownV2",
        )

    # Small pause between messages
    await asyncio.sleep(0.5)

    # Message 2: Next upcoming news
    if next_event:
        msg_next = format_next_event_message(next_event)
        await target_bot.send_message(chat_id=chat_id, text=msg_next, parse_mode="MarkdownV2")
    else:
        await target_bot.send_message(
            chat_id=chat_id,
            text="ℹ️ _Ближайших важных новостей по USD на ближайшие дни не запланировано\\._",
            parse_mode="MarkdownV2",
        )


# ── Command handlers ──────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Greet the user and show past & next news in Yerevan time."""
    text = format_startup_message(config.POLL_INTERVAL_SECONDS)
    await message.answer(text, parse_mode="MarkdownV2")
    await asyncio.sleep(0.5)
    await _send_news_messages(bot, message.chat.id)


@dp.message(Command("news"))
async def cmd_news(message: Message) -> None:
    """Send Message 1 (past news) and Message 2 (upcoming news) in Yerevan time."""
    await _send_news_messages(bot, message.chat.id)


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
        "/news — Прошлая новость и следующая запланированная \\(время Ереван\\)\n"
        "/status — Статистика: проверено событий, отправлено сигналов\n"
        "/start — Перезапуск приветствия и сводки новостей\n"
        "/help — Показать это сообщение"
    )
    await message.answer(help_text, parse_mode="MarkdownV2")


# ── Bot menu registration ─────────────────────────────────────────────────────

async def _set_bot_commands() -> None:
    commands = [
        BotCommand(command="news",   description="Прошлая и следующая новость (Ереван)"),
        BotCommand(command="status", description="Статистика мониторинга"),
        BotCommand(command="start",  description="Запустить бот / сводка новостей"),
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

    # Send startup notification + initial news overview to admin chat
    try:
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=format_startup_message(config.POLL_INTERVAL_SECONDS),
            parse_mode="MarkdownV2",
        )
        await asyncio.sleep(0.8)
        await _send_news_messages(bot, config.ADMIN_CHAT_ID)
    except Exception as exc:
        logger.error("Could not send startup messages: %s", exc)

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

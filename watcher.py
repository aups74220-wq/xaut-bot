"""
watcher.py – Background scheduler that polls Forex Factory and dispatches signals.

Uses APScheduler with the AsyncIOScheduler backend so it integrates naturally
with the aiogram event loop.

State management
────────────────
We keep a dict of {event_id: last_actual_value}.  When an event_id that
previously had an empty actual value now has a filled value, we treat it as a
"new release" and trigger the analysis pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from analyzer import analyze_event
from formatter import format_signal_message
from models import EconomicEvent
from parser import fetch_forexfactory_calendar

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


class CalendarWatcher:
    """
    Periodically fetches the Forex Factory calendar and emits Telegram
    messages whenever a new High-impact USD event releases its actual value.
    """

    def __init__(self, bot: "Bot", admin_chat_id: str, poll_interval: int = 90) -> None:
        self._bot = bot
        self._chat_id = admin_chat_id
        self._poll_interval = poll_interval

        # {event_id: actual_value_string}  – tracks what we have already seen
        self._seen: dict[str, str] = {}

        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._signals_sent: int = 0
        self._events_checked: int = 0
        self._last_check: str = "never"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Register the polling job and start the scheduler."""
        self._scheduler.add_job(
            self._poll,
            trigger="interval",
            seconds=self._poll_interval,
            id="ff_calendar_poll",
            name="Forex Factory Calendar Poll",
            replace_existing=True,
            next_run_time=datetime.now(tz=timezone.utc),  # run immediately on start
        )
        self._scheduler.start()
        logger.info(
            "CalendarWatcher started — polling every %d seconds",
            self._poll_interval,
        )

    def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CalendarWatcher stopped")

    # ── Properties (for /status command) ──────────────────────────────────────

    @property
    def signals_sent(self) -> int:
        return self._signals_sent

    @property
    def events_checked(self) -> int:
        return self._events_checked

    @property
    def last_check(self) -> str:
        return self._last_check

    # ── Core polling logic ────────────────────────────────────────────────────

    async def _poll(self) -> None:
        """
        Fetch the calendar, detect newly-published actuals, and send signals.
        This runs inside the asyncio event loop managed by APScheduler.
        """
        logger.info("Polling Forex Factory calendar…")
        self._last_check = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Run the blocking HTTP fetch in a thread so we don't block the loop
        loop = asyncio.get_event_loop()
        try:
            events: list[EconomicEvent] = await loop.run_in_executor(
                None, fetch_forexfactory_calendar
            )
        except Exception as exc:
            logger.error("Calendar fetch raised an unexpected error: %s", exc, exc_info=True)
            return

        self._events_checked += len(events)

        for event in events:
            await self._process_event(event)

    async def _process_event(self, event: EconomicEvent) -> None:
        """
        Check whether this event is newly released and, if so, analyse and
        send a signal.
        """
        prev_actual = self._seen.get(event.event_id, "")

        # Update our seen-state regardless of whether we send a signal
        self._seen[event.event_id] = event.actual

        # Conditions to trigger a signal:
        #   1. The event now has an actual value.
        #   2. The previously recorded actual was empty (first time we see data).
        if not event.has_actual:
            logger.debug("'%s' — no actual yet, skipping", event.title)
            return

        if prev_actual.strip():
            # We already processed this event in a previous poll
            logger.debug("'%s' — actual unchanged (%r), skipping", event.title, event.actual)
            return

        logger.info("New actual detected for '%s': %r", event.title, event.actual)

        # Analyse
        signal = analyze_event(event)
        if signal is None:
            logger.info("'%s' — analyzer returned no signal", event.title)
            return

        # Format and send
        message = format_signal_message(signal)
        await self._send_message(message)

    async def _send_message(self, text: str) -> None:
        """Send *text* to the configured Telegram chat."""
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="MarkdownV2",
            )
            self._signals_sent += 1
            logger.info("Signal message sent to chat %s", self._chat_id)
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc, exc_info=True)

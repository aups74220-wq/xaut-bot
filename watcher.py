"""
watcher.py – Background scheduler that polls Forex Factory and dispatches signals and reminders.

Uses APScheduler with AsyncIOScheduler integrated into the aiogram event loop.

Key features:
1. Pre-news alerts:
   - 1 hour before news release (~60 min)
   - 30 minutes before news release (~30 min)
   - 5 minutes before news release (~5 min)
2. Post-news trade signals:
   - Immediately when Actual data is published.
   - Calculates deviation vs forecast and gives explicit LONG / SHORT direction for XAUT/USDT.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from analyzer import analyze_event
from formatter import format_pre_news_alert, format_signal_message
from models import EconomicEvent
from parser import fetch_forexfactory_calendar

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


class CalendarWatcher:
    """
    Periodically fetches the Forex Factory calendar and emits Telegram
    messages for pre-news warnings (60m, 30m, 5m) and post-release trade signals.
    """

    def __init__(self, bot: "Bot", admin_chat_id: str, poll_interval: int = 90) -> None:
        self._bot = bot
        self._chat_id = admin_chat_id
        self._poll_interval = poll_interval

        # {event_id: actual_value_string}
        self._seen_actuals: dict[str, str] = {}

        # Set of "{event_id}_{bucket}" to avoid duplicate pre-news alerts
        self._sent_pre_alerts: set[str] = set()

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
            next_run_time=datetime.now(tz=timezone.utc),
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
        Fetch calendar, check pre-news reminders, and detect new actual data.
        """
        logger.info("Polling Forex Factory calendar…")
        self._last_check = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
        1. Check pre-news warnings (60m, 30m, 5m).
        2. Check if actual data is newly published -> trigger trade signal.
        """
        # 1. Pre-news reminders (only for upcoming events without actual published yet)
        if not event.has_actual and event.minutes_until is not None:
            min_left = event.minutes_until

            # 60 minutes reminder (~50 to 65 min)
            if 50.0 <= min_left <= 65.0:
                alert_key = f"{event.event_id}_60"
                if alert_key not in self._sent_pre_alerts:
                    self._sent_pre_alerts.add(alert_key)
                    msg = format_pre_news_alert(event, 60)
                    await self._send_message(msg)

            # 30 minutes reminder (~25 to 35 min)
            elif 25.0 <= min_left <= 35.0:
                alert_key = f"{event.event_id}_30"
                if alert_key not in self._sent_pre_alerts:
                    self._sent_pre_alerts.add(alert_key)
                    msg = format_pre_news_alert(event, 30)
                    await self._send_message(msg)

            # 5 minutes reminder (~2 to 7 min)
            elif 2.0 <= min_left <= 7.0:
                alert_key = f"{event.event_id}_5"
                if alert_key not in self._sent_pre_alerts:
                    self._sent_pre_alerts.add(alert_key)
                    msg = format_pre_news_alert(event, 5)
                    await self._send_message(msg)

        # 2. Actual data published trigger
        prev_actual = self._seen_actuals.get(event.event_id, "")
        self._seen_actuals[event.event_id] = event.actual

        if not event.has_actual:
            return

        if prev_actual.strip():
            # Already handled this release
            return

        logger.info("New actual released for '%s': %r (was empty)", event.title, event.actual)

        # Analyse impact on USD vs Gold
        signal = analyze_event(event)
        if signal is None:
            logger.info("'%s' — analyzer produced no signal", event.title)
            return

        # Format and dispatch trade signal
        message = format_signal_message(signal)
        await self._send_message(message)

    async def _send_message(self, text: str) -> None:
        """Send *text* to the configured Telegram chat."""
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="HTML",
            )
            self._signals_sent += 1
            logger.info("Alert/signal message successfully sent to chat %s", self._chat_id)
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc, exc_info=True)

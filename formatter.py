"""
formatter.py – Telegram message builder.

Produces MarkdownV2-safe messages for aiogram 3.x.
All special characters required by MarkdownV2 are escaped properly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from models import Signal, TradeSignal

# Characters that must be escaped in MarkdownV2
_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

def _escape(text: str) -> str:
    """Escape all MarkdownV2 special characters in *text*."""
    return re.sub(r"([" + re.escape(_SPECIAL_CHARS) + r"])", r"\\\1", text)


def _signal_header(signal: Signal) -> str:
    if signal == Signal.LONG:
        return "📈 ЛОНГ \\(Покупка XAUT/USDT\\)"
    if signal == Signal.SHORT:
        return "📉 ШОРТ \\(Продажа XAUT/USDT\\)"
    return "➡️ НЕЙТРАЛЬНО"


def _signal_emoji(signal: Signal) -> str:
    return {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}.get(signal.value, "⚪")


def format_signal_message(ts: TradeSignal) -> str:
    """
    Build a fully-escaped MarkdownV2 Telegram message for the given TradeSignal.

    Example output (unescaped for readability):
    ─────────────────────────────────────────
    🚨 *ТОРГОВЫЙ СИГНАЛ ПО XAUT/USDT*
    ──────────────────────────────────

    📌 *Событие:* Non-Farm Payrolls
    🕐 *Время:*   8:30am
    📊 *Факт:*    272K   |  *Прогноз:* 185K  |  *Пред.:* 165K

    🎯 *Направление:* 📈 ЛОНГ (Покупка XAUT/USDT)

    💡 *Обоснование:*
    Фактическое значение (272K) +87000.00 (+47.03%) относительно прогноза...

    ⏱ Сгенерировано: 2026-10-02 15:31 UTC
    ─────────────────────────────────────────
    """
    ev = ts.event
    generated = ts.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "🚨 *ТОРГОВЫЙ СИГНАЛ ПО XAUT/USDT*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 *Событие:* {_escape(ev.title)}",
        f"🕐 *Время выхода:* {_escape(ev.event_time)}",
        "",
        (
            f"📊 *Факт:* `{_escape(ev.actual or '—')}`  \\|  "
            f"*Прогноз:* `{_escape(ev.forecast or '—')}`  \\|  "
            f"*Пред\\.:* `{_escape(ev.previous or '—')}`"
        ),
        "",
        f"🎯 *Направление:* {_signal_emoji(ts.signal)} {_signal_header(ts.signal)}",
        "",
        "💡 *Обоснование:*",
        _escape(ts.rationale_ru),
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏱ _Сгенерировано: {_escape(generated)}_",
    ]

    return "\n".join(lines)


def format_startup_message(poll_interval: int) -> str:
    """Confirmation message sent when the bot starts up."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "✅ *XAUT/USDT Signal Bot запущен\\!*\n\n"
        f"🔍 Мониторинг: Forex Factory \\(USD, High Impact\\)\n"
        f"⏰ Интервал проверки: каждые *{_escape(str(poll_interval))} сек*\\.\n"
        f"📡 Актив: *XAUT/USDT* \\(Tether Gold\\)\n\n"
        f"_Старт: {_escape(now)}_"
    )


def format_status_message(
    checked_events: int,
    signals_sent: int,
    last_check: str,
) -> str:
    """Periodic status update (used by /status command)."""
    return (
        "📋 *Статус бота*\n\n"
        f"🔎 Проверено событий сегодня: *{_escape(str(checked_events))}*\n"
        f"📨 Отправлено сигналов: *{_escape(str(signals_sent))}*\n"
        f"🕐 Последняя проверка: {_escape(last_check)}"
    )

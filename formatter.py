"""
formatter.py – Telegram message builder.

Produces MarkdownV2-safe messages for aiogram 3.x.
All special characters required by MarkdownV2 are escaped properly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from models import EconomicEvent, Signal, TradeSignal

# Characters that must be escaped in MarkdownV2
_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def _escape(text: str) -> str:
    """Escape all MarkdownV2 special characters in *text*."""
    return re.sub(r"([" + re.escape(_SPECIAL_CHARS) + r"])", r"\\\1", str(text))


def _signal_header(signal: Signal) -> str:
    if signal == Signal.LONG:
        return "🟢 ЛОНГ / ПОКУПКА \\(ВВЕРХ 📈\\)"
    if signal == Signal.SHORT:
        return "🔴 ШОРТ / ПРОДАЖА \\(ВНИЗ 📉\\)"
    return "⚪ НЕЙТРАЛЬНО \\(ВНЕ РЫНКА ➡️\\)"


def format_pre_news_alert(event: EconomicEvent, minutes_left: int) -> str:
    """
    Alert sent 60m, 30m, and 5m before the scheduled economic news release.
    """
    time_label = f"{minutes_left} минут" if minutes_left != 60 else "1 час (60 мин)"
    lines = [
        "⏳ *ВНИМАНИЕ: СКОРО ВЫХОД НОВОСТЕЙ (USD)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⏱ *До публикации осталось:* ~{_escape(time_label)}",
        f"📌 *Событие:* {_escape(event.title)}",
        f"🕐 *Время выхода:* {_escape(event.event_time)}",
        "",
        (
            f"📊 *Прогноз:* `{_escape(event.forecast or '—')}`  \\|  "
            f"*Пред\\.:* `{_escape(event.previous or '—')}`"
        ),
        "",
        "🎯 *Ожидание по сделке XAUT/USDT:*",
        "• Если факт выйдет *лучше прогноза* \\(сильный USD\\) ➔ сигнал будет *ШОРТ* \\(📉 Вниз\\)\\.",
        "• Если факт выйдет *хуже прогноза* \\(слабый USD\\) ➔ сигнал будет *ЛОНГ* \\(📈 Вверх\\)\\.",
        "",
        "⚠️ _Приготовьте терминал\\. Точный торговый сигнал придет в секунду выхода данных\\!_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_signal_message(ts: TradeSignal) -> str:
    """
    Build a fully-escaped MarkdownV2 Telegram message for the published trade signal.
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
        "🎯 *РЕКОМЕНДАЦИЯ К СДЕЛКЕ:*",
        f"*{_signal_header(ts.signal)}*",
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
        "✅ *XAUT/USDT Signal Bot активен 24/7\\!*\n\n"
        f"🔍 Мониторинг: Forex Factory \\(USD, High Impact\\)\n"
        f"⏰ Интервал проверки: каждые *{_escape(str(poll_interval))} сек*\\.\n"
        f"📡 Актив: *XAUT/USDT* \\(Tether Gold\\)\n"
        "🔔 *Уведомления:* за 1 час, за 30 минут, за 5 минут и в момент публикации\\!\n\n"
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
        f"🔎 Проверено событий: *{_escape(str(checked_events))}*\n"
        f"📨 Отправлено сигналов и предупреждений: *{_escape(str(signals_sent))}*\n"
        f"🕐 Последняя проверка: {_escape(last_check)}"
    )

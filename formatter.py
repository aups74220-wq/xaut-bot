"""
formatter.py – Telegram message builder.

Produces MarkdownV2-safe messages for aiogram 3.x.
All times are explicitly presented in Yerevan time (UTC+4).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from analyzer import analyze_event
from models import EconomicEvent, Signal, TradeSignal

# Characters that must be escaped in MarkdownV2
_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

YEREVAN_TZ = timezone(timedelta(hours=4))


def _escape(text: str) -> str:
    """Escape all MarkdownV2 special characters in *text*."""
    return re.sub(r"([" + re.escape(_SPECIAL_CHARS) + r"])", r"\\\1", str(text))


def _signal_header(signal: Signal) -> str:
    if signal == Signal.LONG:
        return "🟢 ЛОНГ / ПОКУПКА \\(ВВЕРХ 📈\\)"
    if signal == Signal.SHORT:
        return "🔴 ШОРТ / ПРОДАЖА \\(ВНИЗ 📉\\)"
    return "⚪ НЕЙТРАЛЬНО \\(ВНЕ РЫНКА ➡️\\)"


def format_yerevan_time(event: EconomicEvent) -> str:
    """
    Format the event's date and time into Yerevan timezone (UTC+4).
    """
    now_yerevan = datetime.now(YEREVAN_TZ)
    if event.minutes_until is not None:
        ev_dt = now_yerevan + timedelta(minutes=event.minutes_until)
        return ev_dt.strftime("%d.%m.%Y в %H:%M") + " (время Ереван)"
    if event.event_datetime is not None:
        return event.event_datetime.strftime("%d.%m.%Y в %H:%M") + " (время Ереван)"
    return f"{event.event_time} (время Ереван)"


def format_past_event_message(event: EconomicEvent) -> str:
    """
    Message 1: details of the most recent past high-impact USD economic news.
    """
    yerevan_time = format_yerevan_time(event)
    sig = analyze_event(event)

    reaction_text = ""
    if sig:
        reaction_text = sig.rationale_ru
    elif event.has_actual:
        reaction_text = f"Факт: {event.actual} | Прогноз: {event.forecast or '—'}."
    else:
        reaction_text = "Данные опубликованы."

    lines = [
        "📜 *ПРОШЛАЯ НОВОСТЬ (USD)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 *Событие:* {_escape(event.title)}",
        f"🕐 *Была:* {_escape(yerevan_time)}",
        "🔴 *Сила новости:* ВЫСОКАЯ \\(High Impact / Красная\\)",
        "",
        "📊 *Показатели:*",
        f"• *Факт:* `{_escape(event.actual or '—')}`",
        f"• *Прогноз:* `{_escape(event.forecast or '—')}`",
        f"• *Предыдущее:* `{_escape(event.previous or '—')}`",
        "",
        "💡 *Итог реакции рынка:*",
        _escape(reaction_text),
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_next_event_message(event: EconomicEvent) -> str:
    """
    Message 2: details of the next upcoming high-impact USD economic news.
    """
    yerevan_time = format_yerevan_time(event)

    remaining_str = ""
    if event.minutes_until is not None and event.minutes_until > 0:
        total_mins = int(event.minutes_until)
        days = total_mins // (24 * 60)
        hours = (total_mins % (24 * 60)) // 60
        mins = total_mins % 60
        parts = []
        if days > 0:
            parts.append(f"{days} дн.")
        if hours > 0:
            parts.append(f"{hours} ч.")
        parts.append(f"{mins} мин.")
        remaining_str = " ".join(parts)
    else:
        remaining_str = "В ближайшие дни"

    lines = [
        "⏳ *СЛЕДУЮЩАЯ НОВОСТЬ (USD)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 *Событие:* {_escape(event.title)}",
        f"🕐 *Когда выйдет:* {_escape(yerevan_time)}",
        "🔴 *Сила новости:* ВЫСОКАЯ \\(High Impact / Красная\\)",
        f"⏱ *До выхода осталось:* ~{_escape(remaining_str)}",
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
        "🔔 _Бот пришлет напоминания за 1 час, 30 минут и 5 минут до выхода\\!_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_pre_news_alert(event: EconomicEvent, minutes_left: int) -> str:
    """
    Alert sent 60m, 30m, and 5m before the scheduled economic news release.
    """
    time_label = f"{minutes_left} минут" if minutes_left != 60 else "1 час (60 мин)"
    yerevan_time = format_yerevan_time(event)

    lines = [
        "⏳ *ВНИМАНИЕ: СКОРО ВЫХОД НОВОСТЕЙ (USD)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⏱ *До публикации осталось:* ~{_escape(time_label)}",
        f"📌 *Событие:* {_escape(event.title)}",
        f"🕐 *Время выхода:* {_escape(yerevan_time)}",
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
    yerevan_time = format_yerevan_time(ev)

    lines = [
        "🚨 *ТОРГОВЫЙ СИГНАЛ ПО XAUT/USDT*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 *Событие:* {_escape(ev.title)}",
        f"🕐 *Время выхода:* {_escape(yerevan_time)}",
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
    ]

    return "\n".join(lines)


def format_startup_message(poll_interval: int) -> str:
    """Confirmation message sent when the bot starts up."""
    now_yerevan = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M (Ереван)")
    return (
        "✅ *XAUT/USDT Signal Bot активен 24/7\\!*\n\n"
        f"🔍 Мониторинг: Forex Factory \\(USD, High Impact\\)\n"
        f"⏰ Интервал проверки: каждые *{_escape(str(poll_interval))} сек*\\.\n"
        f"📡 Актив: *XAUT/USDT* \\(Tether Gold\\)\n"
        "🔔 *Уведомления:* за 1 час, за 30 мин, за 5 мин и в момент публикации\\!\n"
        "🌍 *Часовой пояс:* Время Ереван \\(UTC\\+4\\)\n\n"
        f"_Старт: {_escape(now_yerevan)}_"
    )


def format_status_message(
    checked_events: int,
    signals_sent: int,
    last_check: str,
) -> str:
    """Periodic status update (used by /status command)."""
    now_yerevan = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M")
    return (
        "📋 *Статус бота*\n\n"
        f"🔎 Проверено событий: *{_escape(str(checked_events))}*\n"
        f"📨 Отправлено сигналов и предупреждений: *{_escape(str(signals_sent))}*\n"
        f"🕐 Текущее время Ереван: *{_escape(now_yerevan)}*\n"
        f"⚡️ Последняя проверка календаря: {_escape(last_check)}"
    )

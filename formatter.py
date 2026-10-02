"""
formatter.py – Telegram message builder.

Uses HTML parse mode for reliable, resilient formatting without entity errors.
All event times are presented in Yerevan time (UTC+4).
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from analyzer import analyze_event
from models import EconomicEvent, Signal, TradeSignal

YEREVAN_TZ = timezone(timedelta(hours=4))


def _esc(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(str(text))


def _signal_header(signal: Signal) -> str:
    if signal == Signal.LONG:
        return "🟢 <b>ЛОНГ / ПОКУПКА (ВВЕРХ 📈)</b>"
    if signal == Signal.SHORT:
        return "🔴 <b>ШОРТ / ПРОДАЖА (ВНИЗ 📉)</b>"
    return "⚪ <b>НЕЙТРАЛЬНО (ВНЕ РЫНКА ➡️)</b>"


def format_yerevan_time(event: EconomicEvent) -> str:
    """Format the event's date and time into Yerevan timezone (UTC+4)."""
    now_yerevan = datetime.now(YEREVAN_TZ)
    if event.minutes_until is not None:
        ev_dt = now_yerevan + timedelta(minutes=event.minutes_until)
        return ev_dt.strftime("%d.%m.%Y в %H:%M") + " (время Ереван)"
    if event.event_datetime is not None:
        return event.event_datetime.strftime("%d.%m.%Y в %H:%M") + " (время Ереван)"
    return f"{event.event_time} (время Ереван)"


def format_past_event_message(event: EconomicEvent) -> str:
    """Message 1: details of the most recent past high-impact USD economic news."""
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
        "📜 <b>ПРОШЛАЯ НОВОСТЬ (USD)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 <b>Событие:</b> {_esc(event.title)}",
        f"🕐 <b>Была:</b> {_esc(yerevan_time)}",
        "🔴 <b>Сила новости:</b> ВЫСОКАЯ (High Impact / Красная)",
        "",
        "📊 <b>Показатели:</b>",
        f"• <b>Факт:</b> <code>{_esc(event.actual or '—')}</code>",
        f"• <b>Прогноз:</b> <code>{_esc(event.forecast or '—')}</code>",
        f"• <b>Предыдущее:</b> <code>{_esc(event.previous or '—')}</code>",
        "",
        "💡 <b>Итог реакции рынка:</b>",
        _esc(reaction_text),
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_next_event_message(event: EconomicEvent) -> str:
    """Message 2: details of the next upcoming high-impact USD economic news."""
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
        "⏳ <b>СЛЕДУЮЩАЯ НОВОСТЬ (USD)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 <b>Событие:</b> {_esc(event.title)}",
        f"🕐 <b>Когда выйдет:</b> {_esc(yerevan_time)}",
        "🔴 <b>Сила новости:</b> ВЫСОКАЯ (High Impact / Красная)",
        f"⏱ <b>До выхода осталось:</b> ~{_esc(remaining_str)}",
        "",
        f"📊 <b>Прогноз:</b> <code>{_esc(event.forecast or '—')}</code>  |  <b>Пред.:</b> <code>{_esc(event.previous or '—')}</code>",
        "",
        "🎯 <b>Ожидание по сделке XAUT/USDT:</b>",
        "• Если факт выйдет <b>лучше прогноза</b> (сильный USD) ➔ сигнал будет <b>ШОРТ (📉 Вниз)</b>.",
        "• Если факт выйдет <b>хуже прогноза</b> (слабый USD) ➔ сигнал будет <b>ЛОНГ (📈 Вверх)</b>.",
        "",
        "🔔 <i>Бот пришлет автоматические напоминания за 1 час, 30 минут и 5 минут до выхода!</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_pre_news_alert(event: EconomicEvent, minutes_left: int) -> str:
    """Alert sent 60m, 30m, and 5m before the scheduled economic news release."""
    time_label = f"{minutes_left} минут" if minutes_left != 60 else "1 час (60 мин)"
    yerevan_time = format_yerevan_time(event)

    lines = [
        "⏳ <b>ВНИМАНИЕ: СКОРО ВЫХОД НОВОСТЕЙ (USD)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⏱ <b>До публикации осталось:</b> ~{_esc(time_label)}",
        f"📌 <b>Событие:</b> {_esc(event.title)}",
        f"🕐 <b>Время выхода:</b> {_esc(yerevan_time)}",
        "🔴 <b>Сила новости:</b> ВЫСОКАЯ (High Impact / Красная)",
        "",
        f"📊 <b>Прогноз:</b> <code>{_esc(event.forecast or '—')}</code>  |  <b>Пред.:</b> <code>{_esc(event.previous or '—')}</code>",
        "",
        "🎯 <b>Ожидание по сделке XAUT/USDT:</b>",
        "• Если факт выйдет <b>лучше прогноза</b> (сильный USD) ➔ сигнал будет <b>ШОРТ (📉 Вниз)</b>.",
        "• Если факт выйдет <b>хуже прогноза</b> (слабый USD) ➔ сигнал будет <b>ЛОНГ (📈 Вверх)</b>.",
        "",
        "⚠️ <i>Приготовьте терминал. Точный торговый сигнал придет в секунду выхода данных!</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_signal_message(ts: TradeSignal) -> str:
    """Build a Telegram HTML message for the published trade signal."""
    ev = ts.event
    yerevan_time = format_yerevan_time(ev)

    lines = [
        "🚨 <b>ТОРГОВЫЙ СИГНАЛ ПО XAUT/USDT</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 <b>Событие:</b> {_esc(ev.title)}",
        f"🕐 <b>Время выхода:</b> {_esc(yerevan_time)}",
        "🔴 <b>Сила новости:</b> ВЫСОКАЯ (High Impact / Красная)",
        "",
        f"📊 <b>Факт:</b> <code>{_esc(ev.actual or '—')}</code>  |  <b>Прогноз:</b> <code>{_esc(ev.forecast or '—')}</code>  |  <b>Пред.:</b> <code>{_esc(ev.previous or '—')}</code>",
        "",
        "🎯 <b>РЕКОМЕНДАЦИЯ К СДЕЛКЕ:</b>",
        f"{_signal_header(ts.signal)}",
        "",
        "💡 <b>Обоснование:</b>",
        _esc(ts.rationale_ru),
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_startup_message(poll_interval: int) -> str:
    """Confirmation message sent when the bot starts up."""
    now_yerevan = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M (Ереван)")
    return (
        "✅ <b>XAUT/USDT Signal Bot активен 24/7!</b>\n\n"
        f"🔍 Мониторинг: Forex Factory (USD, High Impact)\n"
        f"⏰ Интервал проверки: каждые <b>{poll_interval} сек</b>.\n"
        f"📡 Актив: <b>XAUT/USDT</b> (Tether Gold)\n"
        "🔔 <b>Уведомления:</b> за 1 час, за 30 мин, за 5 мин и в момент публикации!\n"
        "🌍 <b>Часовой пояс:</b> Время Ереван (UTC+4)\n\n"
        f"<i>Старт: {now_yerevan}</i>"
    )


def format_status_message(
    checked_events: int,
    signals_sent: int,
    last_check: str,
) -> str:
    """Periodic status update (used by /status command)."""
    now_yerevan = datetime.now(YEREVAN_TZ).strftime("%d.%m.%Y %H:%M")
    return (
        "📋 <b>Статус бота</b>\n\n"
        f"🔎 Проверено событий: <b>{checked_events}</b>\n"
        f"📨 Отправлено сигналов и предупреждений: <b>{signals_sent}</b>\n"
        f"🕐 Текущее время Ереван: <b>{now_yerevan}</b>\n"
        f"⚡️ Последняя проверка календаря: {_esc(last_check)}"
    )

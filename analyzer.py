"""
analyzer.py – Economic data comparison & XAUT/USDT signal engine.

Logic overview
──────────────
Gold (XAU) has an inverse relationship with the US Dollar:
  • Stronger USD  →  lower gold  →  SHORT XAUT/USDT
  • Weaker USD    →  higher gold →  LONG  XAUT/USDT

For each high-impact USD event we:
  1. Parse actual and forecast values into floats.
  2. Determine whether the metric is "USD-positive when higher" or
     "USD-positive when lower" (see INVERSE_METRICS).
  3. Compute the deviation direction and produce a Signal.
  4. Build a Russian-language rationale string.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from models import EconomicEvent, Signal, TradeSignal

logger = logging.getLogger(__name__)

# ── Metrics that are USD-bearish when they beat forecasts ─────────────────────
# (e.g. Unemployment Rate: high actual = bad for USD)
_INVERSE_METRICS: frozenset[str] = frozenset(
    {
        "unemployment rate",
        "jobless claims",
        "initial jobless claims",
        "continuing jobless claims",
        "trade deficit",
        "trade balance",         # negative value — larger deficit = worse
        "budget deficit",
        "current account",       # usually negative — larger = worse for USD
    }
)

# ── Events whose signal direction is ambiguous / always neutral ───────────────
_NEUTRAL_METRICS: frozenset[str] = frozenset(
    {
        "fed speakers",
        "fomc minutes",          # qualitative – can't parse a number
        "beige book",
    }
)

# ── Threshold: minimum relative deviation to issue a signal (%) ──────────────
_MIN_DEVIATION_PCT: float = 0.05   # 0.05 % – effectively catches almost anything

# ── Emojis for direction ──────────────────────────────────────────────────────
_EMOJI_LONG  = "📈"
_EMOJI_SHORT = "📉"
_EMOJI_NEUTRAL = "➡️"


def _strip_to_float(raw: str) -> Optional[float]:
    """
    Convert strings like '223K', '-0.3%', '5.25', '1.2M', '3B' to float.
    Returns None if the string cannot be parsed.
    """
    if not raw:
        return None

    s = raw.strip().replace(",", "").upper()

    # Handle percentage – strip the '%' sign
    s = s.replace("%", "")

    # Handle multiplier suffixes
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            try:
                return float(s[:-1]) * mult
            except ValueError:
                return None

    try:
        return float(s)
    except ValueError:
        return None


def _is_inverse(title: str) -> bool:
    """Return True if a higher-than-forecast reading is USD-bearish."""
    lower_title = title.lower()
    return any(keyword in lower_title for keyword in _INVERSE_METRICS)


def _is_neutral_event(title: str) -> bool:
    """Return True for events that can never produce a directional signal."""
    lower_title = title.lower()
    return any(keyword in lower_title for keyword in _NEUTRAL_METRICS)


def _build_rationale(
    event: EconomicEvent,
    actual: float,
    forecast: float,
    signal: Signal,
) -> str:
    """
    Build a human-readable Russian rationale for the trade signal.
    """
    deviation = actual - forecast
    pct = (deviation / abs(forecast) * 100) if forecast != 0 else 0.0
    sign = "+" if deviation >= 0 else ""

    if signal == Signal.LONG:
        usd_move = "ослабевает"
        gold_move = "укрепляется"
        direction_label = f"{_EMOJI_LONG} ЛОНГ"
    elif signal == Signal.SHORT:
        usd_move = "укрепляется"
        gold_move = "корректируется вниз"
        direction_label = f"{_EMOJI_SHORT} ШОРТ"
    else:
        return "Отклонение незначительно — нейтральный сигнал."

    return (
        f"Фактическое значение ({event.actual}) {sign}{deviation:.2f} "
        f"({sign}{pct:.2f}%) относительно прогноза ({event.forecast}). "
        f"Доллар {usd_move}, золото {gold_move}. "
        f"Рекомендация: {direction_label} по {'{PAIR}'}."
    ).replace("{PAIR}", "XAUT/USDT")


def analyze_event(event: EconomicEvent) -> Optional[TradeSignal]:
    """
    Core analysis function.  Returns a TradeSignal or None if inconclusive.

    Steps:
      1. Ensure the event has an actual value (i.e. it was just released).
      2. Parse actual and forecast to floats.
      3. Apply direction logic (including inverse-metric handling).
      4. Build the signal + rationale.
    """
    if not event.has_actual:
        logger.debug("Skipping '%s' — no actual value yet", event.title)
        return None

    if _is_neutral_event(event.title):
        logger.info("'%s' is a qualitative event — skipping", event.title)
        return None

    actual   = _strip_to_float(event.actual)
    forecast = _strip_to_float(event.forecast)

    # Need both values to compare
    if actual is None:
        logger.warning("Could not parse actual value for '%s': %r", event.title, event.actual)
        return None

    if forecast is None:
        # No forecast available – can't determine direction
        logger.info("No forecast for '%s' — cannot generate directional signal", event.title)
        return TradeSignal(
            event=event,
            signal=Signal.NEUTRAL,
            rationale_ru=(
                f"Прогноз недоступен. Факт: {event.actual}. "
                "Направление торговли определить невозможно."
            ),
        )

    deviation = actual - forecast
    deviation_pct = abs(deviation / forecast * 100) if forecast != 0 else 0.0

    # Too small to matter
    if deviation_pct < _MIN_DEVIATION_PCT:
        logger.info(
            "'%s' deviation %.4f%% below threshold — NEUTRAL",
            event.title,
            deviation_pct,
        )
        return TradeSignal(
            event=event,
            signal=Signal.NEUTRAL,
            rationale_ru=(
                f"Данные почти совпадают с прогнозом (отклонение {deviation_pct:.2f}%). "
                "Значимого движения не ожидается."
            ),
        )

    # Determine raw direction: positive deviation = actual beat forecast
    beat_forecast = deviation > 0

    # Inverse metrics: beating forecast is USD-bearish
    inverse = _is_inverse(event.title)

    # USD strengthens when:
    #   normal metric → actual > forecast  (beat_forecast=True, inverse=False)
    #   inverse metric → actual < forecast (beat_forecast=False, inverse=True)
    usd_bullish = beat_forecast ^ inverse   # XOR

    if usd_bullish:
        signal = Signal.SHORT  # Strong USD → gold falls
    else:
        signal = Signal.LONG   # Weak USD → gold rises

    rationale = _build_rationale(event, actual, forecast, signal)
    logger.info(
        "Signal for '%s': %s (actual=%s forecast=%s deviation=%.2f%%)",
        event.title,
        signal.value,
        event.actual,
        event.forecast,
        deviation_pct,
    )
    return TradeSignal(event=event, signal=signal, rationale_ru=rationale)

"""
models.py – Plain data classes shared across modules.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Impact(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NON_ECONOMIC = "non-economic"
    UNKNOWN = "unknown"


class Signal(str, Enum):
    LONG = "LONG"   # Buy XAUT/USDT  – gold expected to rise
    SHORT = "SHORT"  # Sell XAUT/USDT – gold expected to fall
    NEUTRAL = "NEUTRAL"  # Data matches forecast or inconclusive


@dataclass
class EconomicEvent:
    """Represents a single row from the Forex Factory calendar."""

    event_id: str           # Unique identifier (date + title hash)
    title: str              # Event title, e.g. "Non-Farm Payrolls"
    currency: str           # "USD", "EUR", etc.
    impact: Impact          # High / Medium / Low
    actual: str             # Raw string from the page (empty before release)
    forecast: str           # Raw string from the page
    previous: str           # Raw string from the page
    event_time: str         # Human-readable time string from the page
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def has_actual(self) -> bool:
        """True once the actual value has been published."""
        return bool(self.actual.strip())

    def __repr__(self) -> str:
        return (
            f"<EconomicEvent '{self.title}' "
            f"actual={self.actual!r} forecast={self.forecast!r}>"
        )


@dataclass
class TradeSignal:
    """The output produced by the analysis engine."""

    event: EconomicEvent
    signal: Signal
    rationale_ru: str       # Russian-language explanation for the Telegram alert
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

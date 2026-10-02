"""
test_analyzer.py – Unit tests for the analysis engine.
Run with: py -m pytest tests/ -v
"""

import pytest
from models import EconomicEvent, Impact, Signal
from analyzer import analyze_event, _strip_to_float


# ── Number parser tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("272K",   272_000.0),
    ("1.2M",   1_200_000.0),
    ("3B",     3_000_000_000.0),
    ("-0.3%",  -0.3),
    ("5.25",   5.25),
    ("",       None),
    ("n/a",    None),
    ("3.5T",   3_500_000_000_000.0),
])
def test_strip_to_float(raw, expected):
    assert _strip_to_float(raw) == expected


# ── Helper to build a minimal EconomicEvent ───────────────────────────────────

def _event(title: str, actual: str, forecast: str, previous: str = "0") -> EconomicEvent:
    return EconomicEvent(
        event_id="test123",
        title=title,
        currency="USD",
        impact=Impact.HIGH,
        actual=actual,
        forecast=forecast,
        previous=previous,
        event_time="8:30am",
    )


# ── Signal direction tests ────────────────────────────────────────────────────

class TestNFP:
    """Non-Farm Payrolls: higher actual = stronger USD = SHORT gold."""

    def test_beat_forecast_is_short(self):
        ev = _event("Non-Farm Payrolls", actual="272K", forecast="185K")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.SHORT

    def test_miss_forecast_is_long(self):
        ev = _event("Non-Farm Payrolls", actual="150K", forecast="185K")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.LONG


class TestCPI:
    """CPI: higher actual = inflationary → Fed hawks → stronger USD → SHORT gold."""

    def test_hot_cpi_is_short(self):
        ev = _event("CPI m/m", actual="0.4%", forecast="0.2%")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.SHORT

    def test_cool_cpi_is_long(self):
        ev = _event("CPI y/y", actual="2.8%", forecast="3.2%")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.LONG


class TestUnemploymentRate:
    """Unemployment Rate is an inverse metric: higher = bad for USD → LONG gold."""

    def test_higher_unemployment_is_long(self):
        ev = _event("Unemployment Rate", actual="4.2%", forecast="3.9%")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.LONG

    def test_lower_unemployment_is_short(self):
        ev = _event("Unemployment Rate", actual="3.7%", forecast="3.9%")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.SHORT


class TestEdgeCases:
    """Edge case handling."""

    def test_no_actual_returns_none(self):
        ev = _event("Non-Farm Payrolls", actual="", forecast="185K")
        ts = analyze_event(ev)
        assert ts is None

    def test_no_forecast_is_neutral(self):
        ev = _event("Non-Farm Payrolls", actual="272K", forecast="")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.NEUTRAL

    def test_exact_match_is_neutral(self):
        ev = _event("GDP q/q", actual="2.5%", forecast="2.5%")
        ts = analyze_event(ev)
        assert ts is not None
        assert ts.signal == Signal.NEUTRAL

    def test_qualitative_event_skipped(self):
        ev = _event("FOMC Minutes", actual="hawkish", forecast="")
        ts = analyze_event(ev)
        assert ts is None

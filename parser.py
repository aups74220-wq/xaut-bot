"""
parser.py – Forex Factory calendar scraper.

Forex Factory serves its calendar as an HTML table.  Because the site uses
Cloudflare and requires JS for full rendering, we target its JSON calendar
endpoint first (undocumented but stable), falling back to HTML parsing.

Endpoint: https://www.forexfactory.com/calendar.json
          Returns the current week's events as a JSON array.

HTML fallback: https://www.forexfactory.com/calendar
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Detect the best available HTML parser (lxml is faster but optional).
# Falls back gracefully to Python's built-in html.parser.
try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except ImportError:
    _HTML_PARSER = "html.parser"

from config import FF_CALENDAR_URL, HTTP_PROXY
from models import EconomicEvent, Impact

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_JSON_URL = "https://www.forexfactory.com/calendar.json"
_REQUEST_TIMEOUT = 20          # seconds
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 5             # seconds between retries

# Forex Factory impact class names → our enum
_IMPACT_MAP: dict[str, Impact] = {
    "high":          Impact.HIGH,
    "medium":        Impact.MEDIUM,
    "low":           Impact.LOW,
    "non-economic":  Impact.NON_ECONOMIC,
}

_ua = UserAgent()


def _build_session() -> requests.Session:
    """Create a requests session with browser-like headers and optional proxy."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _ua.random,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/html, */*",
            "Referer": "https://www.forexfactory.com/",
        }
    )
    if HTTP_PROXY:
        session.proxies = {"http": HTTP_PROXY, "https": HTTP_PROXY}
    return session


def _make_event_id(event_date: str, title: str) -> str:
    """Stable deterministic ID for deduplication purposes."""
    raw = f"{event_date}::{title.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# JSON endpoint (primary)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_impact_json(impact_str: str) -> Impact:
    """Map Forex Factory JSON impact value to our enum."""
    return _IMPACT_MAP.get(impact_str.lower(), Impact.UNKNOWN)


def _fetch_json_calendar(session: requests.Session) -> list[EconomicEvent]:
    """
    Fetch the Forex Factory JSON calendar endpoint.
    Returns a (possibly empty) list of EconomicEvent objects.
    """
    # FF JSON endpoint format: ?day=oct2.2026 (lowercase month, no leading zero)
    today = date.today()
    day_str = f"{today.strftime('%b').lower()}{today.day}.{today.year}"
    url = f"{_JSON_URL}?day={day_str}"

    logger.debug("Fetching JSON calendar: %s", url)
    response = session.get(url, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()

    data: list[dict] = response.json()
    events: list[EconomicEvent] = []

    for item in data:
        currency: str = item.get("currency", "").upper()
        impact_raw: str = item.get("impact", "").lower()
        impact = _parse_impact_json(impact_raw)

        # We only care about High-impact USD events
        if currency != "USD" or impact != Impact.HIGH:
            continue

        title: str = item.get("name", "").strip()
        event_date: str = item.get("date", today)

        events.append(
            EconomicEvent(
                event_id=_make_event_id(event_date, title),
                title=title,
                currency=currency,
                impact=impact,
                actual=item.get("actual", "") or "",
                forecast=item.get("forecast", "") or "",
                previous=item.get("previous", "") or "",
                event_time=item.get("time", ""),
            )
        )

    logger.info("JSON parser: found %d high-impact USD events", len(events))
    return events


# ─────────────────────────────────────────────────────────────────────────────
# HTML fallback (BeautifulSoup)
# ─────────────────────────────────────────────────────────────────────────────

def _cell_text(cell) -> str:
    """Return cleaned inner text of a <td> element."""
    if cell is None:
        return ""
    return cell.get_text(separator=" ", strip=True)


def _parse_impact_html(row) -> Impact:
    """Detect impact level from the icon <td> class attributes."""
    impact_td = row.find("td", class_=re.compile(r"calendar__impact"))
    if not impact_td:
        return Impact.UNKNOWN
    span = impact_td.find("span")
    if not span:
        return Impact.UNKNOWN
    classes = " ".join(span.get("class", []))
    for key, val in _IMPACT_MAP.items():
        if key in classes:
            return val
    return Impact.UNKNOWN


def _fetch_html_calendar(session: requests.Session) -> list[EconomicEvent]:
    """
    Scrape the Forex Factory HTML calendar page.
    Falls back to this when the JSON endpoint is unavailable.
    """
    logger.debug("Fetching HTML calendar: %s", FF_CALENDAR_URL)
    response = session.get(FF_CALENDAR_URL, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, _HTML_PARSER)
    table = soup.find("table", class_=re.compile(r"calendar__table"))
    if table is None:
        logger.warning("HTML parser: could not locate calendar table")
        return []

    events: list[EconomicEvent] = []
    current_date = date.today().isoformat()

    for row in table.find_all("tr", class_=re.compile(r"calendar__row")):
        # Rows that carry a date update current_date
        date_td = row.find("td", class_=re.compile(r"calendar__date"))
        if date_td and date_td.get_text(strip=True):
            current_date = date_td.get_text(strip=True)

        currency_td = row.find("td", class_=re.compile(r"calendar__currency"))
        if not currency_td:
            continue
        currency = _cell_text(currency_td).upper()
        if currency != "USD":
            continue

        impact = _parse_impact_html(row)
        if impact != Impact.HIGH:
            continue

        title_td = row.find("td", class_=re.compile(r"calendar__event"))
        time_td = row.find("td", class_=re.compile(r"calendar__time"))
        actual_td = row.find("td", class_=re.compile(r"calendar__actual"))
        forecast_td = row.find("td", class_=re.compile(r"calendar__forecast"))
        previous_td = row.find("td", class_=re.compile(r"calendar__previous"))

        title = _cell_text(title_td)
        if not title:
            continue

        events.append(
            EconomicEvent(
                event_id=_make_event_id(current_date, title),
                title=title,
                currency=currency,
                impact=impact,
                actual=_cell_text(actual_td),
                forecast=_cell_text(forecast_td),
                previous=_cell_text(previous_td),
                event_time=_cell_text(time_td),
            )
        )

    logger.info("HTML parser: found %d high-impact USD events", len(events))
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_forexfactory_calendar() -> list[EconomicEvent]:
    """
    Fetch today's high-impact USD events from Forex Factory.

    Strategy:
      1. Try the undocumented JSON endpoint (fast, structured).
      2. If that fails, fall back to HTML scraping.
      3. Retry up to _RETRY_ATTEMPTS times on network errors.

    Returns a list of EconomicEvent objects (may be empty).
    """
    session = _build_session()
    last_exc: Optional[Exception] = None

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            # Attempt 1: JSON endpoint
            try:
                return _fetch_json_calendar(session)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "JSON endpoint parse error (%s); switching to HTML fallback",
                    exc,
                )
            # Attempt 2: HTML fallback
            return _fetch_html_calendar(session)

        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Network error on attempt %d/%d: %s",
                attempt,
                _RETRY_ATTEMPTS,
                exc,
            )
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)

    logger.error("All %d fetch attempts failed: %s", _RETRY_ATTEMPTS, last_exc)
    return []

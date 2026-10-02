"""
parser.py – Forex Factory calendar scraper.

Extracts USD High-impact economic news events from Forex Factory calendar.
Includes support for:
- Red impact (High impact) detection via CSS icons.
- Parsing event date and time into Python datetime objects.
- Calculating minutes remaining until the event based on the page's current clock.
- Retrieving actual, forecast, and previous values.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from config import FF_CALENDAR_URL, HTTP_PROXY
from models import EconomicEvent, Impact

# Detect best available HTML parser
try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except ImportError:
    _HTML_PARSER = "html.parser"

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 20
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 3

_ua = UserAgent()


def _build_session() -> requests.Session:
    """Create a requests session with browser-like headers and optional proxy."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _ua.random,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.forexfactory.com/",
        }
    )
    if HTTP_PROXY:
        session.proxies = {"http": HTTP_PROXY, "https": HTTP_PROXY}
    return session


def _parse_ff_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Parse strings like date_str='Fri Oct 2', time_str='8:30am' or '4:30pm' into datetime.
    """
    if not date_str or not time_str:
        return None
    try:
        parts = date_str.strip().split()
        if len(parts) < 3:
            return None
        month_day = f"{parts[1]} {parts[2]}"
        year = date.today().year
        time_clean = time_str.strip().lower()
        full_str = f"{month_day} {year} {time_clean}"
        return datetime.strptime(full_str, "%b %d %Y %I:%M%p")
    except Exception:
        return None


def _get_page_clock(soup: BeautifulSoup) -> datetime:
    """
    Read the current server time from the page header clock.
    Ensures exact synchronization with event times regardless of local timezone.
    """
    ht = soup.find("a", class_=lambda c: c and "calendar__header-time" in c)
    if not ht or not ht.text.strip():
        return datetime.now()
    t_str = ht.text.strip().lower()
    d_str = date.today().strftime("%b %d %Y")
    try:
        return datetime.strptime(f"{d_str} {t_str}", "%b %d %Y %I:%M%p")
    except Exception:
        return datetime.now()


def _cell_text(cell) -> str:
    """Return cleaned inner text of a <td> element."""
    if cell is None:
        return ""
    return cell.get_text(separator=" ", strip=True)


def _fetch_html_calendar(session: requests.Session) -> list[EconomicEvent]:
    """
    Scrape the Forex Factory HTML calendar page.
    Extracts high-impact USD events with date/time, remaining minutes, actual, forecast, and previous data.
    """
    logger.debug("Fetching HTML calendar: %s", FF_CALENDAR_URL)
    response = session.get(FF_CALENDAR_URL, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, _HTML_PARSER)
    rows = soup.find_all("tr", class_=lambda c: c and "calendar__row" in c)
    if not rows:
        logger.warning("HTML parser: could not locate any calendar rows")
        return []

    page_clock = _get_page_clock(soup)
    events: list[EconomicEvent] = []
    curr_date_str = ""
    curr_time_str = ""

    for tr in rows:
        # Update current date if row has date cell
        dt_td = tr.find("td", class_=lambda c: c and "calendar__date" in c)
        if dt_td and dt_td.text.strip():
            curr_date_str = dt_td.text.strip()

        # Update current time if row has time cell
        tm_td = tr.find("td", class_=lambda c: c and "calendar__time" in c)
        if tm_td and tm_td.text.strip():
            curr_time_str = tm_td.text.strip()

        # Filter: High Impact only (red icon)
        imp_td = tr.find("td", class_=lambda c: c and "calendar__impact" in c)
        if not imp_td or "icon--ff-impact-red" not in str(imp_td):
            continue

        # Filter: USD currency only
        curr_td = tr.find("td", class_=lambda c: c and "calendar__currency" in c)
        if not curr_td or curr_td.text.strip().upper() != "USD":
            continue

        ev_td = tr.find("td", class_=lambda c: c and "calendar__event" in c)
        act_td = tr.find("td", class_=lambda c: c and "calendar__actual" in c)
        fc_td = tr.find("td", class_=lambda c: c and "calendar__forecast" in c)
        prv_td = tr.find("td", class_=lambda c: c and "calendar__previous" in c)

        title = _cell_text(ev_td)
        if not title:
            continue

        actual = _cell_text(act_td)
        forecast = _cell_text(fc_td)
        previous = _cell_text(prv_td)

        event_id = tr.get("data-event-id")
        if not event_id:
            raw_id = f"{curr_date_str}::{title.strip().lower()}"
            event_id = hashlib.md5(raw_id.encode()).hexdigest()[:12]

        event_dt = _parse_ff_datetime(curr_date_str, curr_time_str)
        minutes_until: Optional[float] = None
        if event_dt and page_clock:
            minutes_until = (event_dt - page_clock).total_seconds() / 60.0

        events.append(
            EconomicEvent(
                event_id=str(event_id),
                title=title,
                currency="USD",
                impact=Impact.HIGH,
                actual=actual,
                forecast=forecast,
                previous=previous,
                event_time=f"{curr_date_str} {curr_time_str}".strip(),
                event_datetime=event_dt,
                minutes_until=minutes_until,
            )
        )

    logger.info("Forex Factory scraper: found %d high-impact USD events (page clock: %s)", len(events), page_clock)
    return events


def fetch_forexfactory_calendar() -> list[EconomicEvent]:
    """
    Fetch high-impact USD events with retries.
    """
    session = _build_session()
    last_exc: Optional[Exception] = None

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            return _fetch_html_calendar(session)
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Scraper network error on attempt %d/%d: %s", attempt, _RETRY_ATTEMPTS, exc)
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)

    logger.error("Scraper failed after %d attempts: %s", _RETRY_ATTEMPTS, last_exc)
    return []

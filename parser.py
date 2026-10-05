"""
parser.py – Forex Factory calendar scraper.

Extracts USD High-impact economic news events from Forex Factory calendar.
Includes support for:
- Cloudflare bypass via curl_cffi Chrome impersonation (with requests fallback).
- Red impact (High impact) detection via CSS icons.
- Parsing event date and time into Python datetime objects.
- Calculating minutes remaining until the event based on the page's current clock.
- Retrieving actual, forecast, and previous values.
- Seamless past/next news lookup across week boundaries (this week, last week, next week).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime
from typing import Optional

try:
    from curl_cffi import requests as curl_requests
    _HAVE_CURL_CFFI = True
except ImportError:
    import requests as curl_requests
    _HAVE_CURL_CFFI = False

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

_REQUEST_TIMEOUT = 25
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 3

_ua = UserAgent()


def _build_session() -> requests.Session:
    """Create a standard requests session with browser-like headers."""
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


def _fetch_html_calendar(url: str = FF_CALENDAR_URL) -> list[EconomicEvent]:
    """
    Scrape the Forex Factory HTML calendar page.
    Uses curl_cffi for transparent Cloudflare bypass, falling back to requests.
    """
    logger.debug("Fetching HTML calendar from: %s", url)

    response_text = ""
    if _HAVE_CURL_CFFI:
        proxies = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else None
        res = curl_requests.get(
            url,
            impersonate="chrome",
            timeout=_REQUEST_TIMEOUT,
            proxies=proxies,
        )
        res.raise_for_status()
        response_text = res.text
    else:
        session = _build_session()
        res = session.get(url, timeout=_REQUEST_TIMEOUT)
        res.raise_for_status()
        response_text = res.text

    soup = BeautifulSoup(response_text, _HTML_PARSER)
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

    logger.info("Forex Factory scraper: found %d high-impact USD events for %s", len(events), url)
    return events


def fetch_forexfactory_calendar(url: str = FF_CALENDAR_URL) -> list[EconomicEvent]:
    """
    Fetch high-impact USD events with retries.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            return _fetch_html_calendar(url=url)
        except Exception as exc:
            last_exc = exc
            logger.warning("Scraper error on attempt %d/%d: %s", attempt, _RETRY_ATTEMPTS, exc)
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF)

    logger.error("Scraper failed after %d attempts: %s", _RETRY_ATTEMPTS, last_exc)
    return []


def get_past_and_next_events() -> tuple[Optional[EconomicEvent], Optional[EconomicEvent]]:
    """
    Identify:
    1. The most recent past high-impact USD event.
       (If none yet this week, looks back at last week's calendar).
    2. The next upcoming high-impact USD event.
       (If none left this week, looks forward at next week's calendar).
    """
    this_week_events = fetch_forexfactory_calendar(FF_CALENDAR_URL)

    past_events = [
        e for e in this_week_events
        if e.has_actual or (e.minutes_until is not None and e.minutes_until <= 0)
    ]
    future_events = [
        e for e in this_week_events
        if not e.has_actual and (e.minutes_until is not None and e.minutes_until > 0)
    ]

    last_past = past_events[-1] if past_events else None
    next_future = future_events[0] if future_events else None

    # If no past events found this week (e.g. early Monday morning), look at last week
    if last_past is None:
        try:
            last_week_events = fetch_forexfactory_calendar("https://www.forexfactory.com/calendar?week=last")
            last_week_past = [
                e for e in last_week_events
                if e.has_actual or (e.minutes_until is not None and e.minutes_until <= 0)
            ]
            if last_week_past:
                last_past = last_week_past[-1]
        except Exception as exc:
            logger.error("Failed to fetch last week's events: %s", exc)

    # If no upcoming events left this week (e.g. weekend), look at next week
    if next_future is None:
        try:
            next_week_events = fetch_forexfactory_calendar("https://www.forexfactory.com/calendar?week=next")
            next_future_candidates = [
                e for e in next_week_events
                if not e.has_actual
            ]
            if next_future_candidates:
                next_future = next_future_candidates[0]
        except Exception as exc:
            logger.error("Failed to fetch next week's events: %s", exc)

    return last_past, next_future

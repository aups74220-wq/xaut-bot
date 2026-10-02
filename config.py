"""
config.py – Centralised configuration loader.
Reads environment variables from a .env file (or the system environment).
"""

import os
import logging
from dotenv import load_dotenv

# Load .env from the project root (one level up from this file, or CWD)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def _require(var: str) -> str:
    """Return the value of *var* or raise RuntimeError if it is not set."""
    value = os.getenv(var, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable '{var}' is not set. "
            "Check your .env file."
        )
    return value


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID: str = _require("ADMIN_CHAT_ID")

# ── Scheduler ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "90"))

# ── Network ───────────────────────────────────────────────────────────────────
HTTP_PROXY: str | None = os.getenv("HTTP_PROXY", "").strip() or None

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Forex Factory ─────────────────────────────────────────────────────────────
FF_CALENDAR_URL: str = "https://www.forexfactory.com/calendar"

# ── Trading pair ──────────────────────────────────────────────────────────────
TRADING_PAIR: str = "XAUT/USDT"


def configure_logging() -> None:
    """Apply a consistent log format across the whole application."""
    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

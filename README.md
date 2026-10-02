# XAUT/USDT Forex Factory Trading Signal Bot

An automated Python trading-signal bot that monitors the **Forex Factory** macroeconomic calendar for high-impact USD events, compares actual vs. forecast values, and sends formatted trading signals for **XAUT/USDT (Tether Gold)** to a Telegram channel.

---

## Architecture

```
xaut_bot/
├── bot.py          ← Entry point · aiogram 3 Dispatcher · /start /status /help
├── watcher.py      ← APScheduler background loop · new-actual detection
├── parser.py       ← Forex Factory scraper (JSON + HTML fallback, retries)
├── analyzer.py     ← USD/gold divergence logic · number parser · rationale builder
├── formatter.py    ← MarkdownV2 Telegram message formatter
├── models.py       ← EconomicEvent · TradeSignal · Signal / Impact enums
├── config.py       ← .env loader · validated required variables
├── requirements.txt
├── .env.example
└── tests/
    ├── conftest.py
    └── test_analyzer.py
```

### Data Flow

```
APScheduler (every 90 s)
        │
        ▼
  parser.py  ──JSON endpoint──▶  list[EconomicEvent]  (USD, High-impact only)
                └─HTML fallback─▶
        │
        ▼
  watcher.py  ──  detect new actual value
        │
        ▼
  analyzer.py ──  compare Actual vs Forecast
        │              ├─ Strong USD  →  SHORT XAUT/USDT
        │              └─ Weak USD    →  LONG  XAUT/USDT
        ▼
  formatter.py ── MarkdownV2 message
        │
        ▼
  Telegram Bot API  ──▶  ADMIN_CHAT_ID
```

---

## Quick Start

### 1. Clone / download the project

```bash
git clone <repo-url>
cd xaut_bot
```

### 2. Create a virtual environment

```bash
py -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/macOS
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
copy .env.example .env      # Windows
# cp .env.example .env       # Linux/macOS
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGhijklmnop...   # from @BotFather
ADMIN_CHAT_ID=-1001234567890                        # channel/group ID
POLL_INTERVAL_SECONDS=90                            # check every 90 s
HTTP_PROXY=                                         # leave empty or set proxy
LOG_LEVEL=INFO
```

> **Tip — finding your chat ID:**  
> Forward any message from your channel to [@userinfobot](https://t.me/userinfobot).  
> For channels, the ID starts with `-100`.

### 5. Run the bot

```bash
py bot.py
```

---

## Signal Logic

| Event Type | Actual > Forecast | Signal | Reason |
|---|---|---|---|
| NFP, GDP, CPI, Retail Sales, ISM… | ✅ Beat | 📉 **SHORT** XAUT | Strong USD → gold falls |
| NFP, GDP, CPI, Retail Sales, ISM… | ❌ Miss | 📈 **LONG** XAUT | Weak USD → gold rises |
| Unemployment Rate, Jobless Claims | ✅ Beat | 📈 **LONG** XAUT | High unemployment = weak USD |
| Unemployment Rate, Jobless Claims | ❌ Miss | 📉 **SHORT** XAUT | Low unemployment = strong USD |
| Forecast missing | Any | ➡️ **NEUTRAL** | Cannot determine direction |
| FOMC Minutes, Fed Speakers | Any | *(skipped)* | Qualitative, not parseable |

---

## Sample Telegram Alert

```
🚨 ТОРГОВЫЙ СИГНАЛ ПО XAUT/USDT
━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Событие: Non-Farm Payrolls
🕐 Время выхода: 8:30am

📊 Факт: 272K  |  Прогноз: 185K  |  Пред.: 165K

🎯 Направление: 🔴 📉 ШОРТ (Продажа XAUT/USDT)

💡 Обоснование:
Фактическое значение (272K) +87000.00 (+47.03%) относительно прогноза (185K).
Доллар укрепляется, золото корректируется вниз.
Рекомендация: 📉 ШОРТ по XAUT/USDT.

━━━━━━━━━━━━━━━━━━━━━━━━━
⏱ Сгенерировано: 2026-10-02 15:31 UTC
```

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Confirm the bot is running and show config |
| `/status` | Events checked, signals sent, last poll time |
| `/help` | Show available commands |

---

## Running Tests

```bash
py -m pytest tests/ -v
```

---

## Notes & Limitations

- **Forex Factory blocks scrapers** aggressively with Cloudflare. The bot uses
  a random `User-Agent` and targets the JSON endpoint first. If you get blocked
  frequently, set `HTTP_PROXY` to route through a residential proxy or VPN.
- Signals are **informational only** — not financial advice. Always apply your
  own risk management before trading.
- The bot is designed for **spot / perpetual futures** XAUT/USDT pairs on
  exchanges such as Binance, OKX, Bybit, etc. Entry timing, SL/TP, and
  position sizing are left to the trader.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `ADMIN_CHAT_ID` | ✅ | — | Chat/channel ID to receive signals |
| `POLL_INTERVAL_SECONDS` | ❌ | `90` | Seconds between calendar checks |
| `HTTP_PROXY` | ❌ | — | HTTP/HTTPS proxy URL |
| `LOG_LEVEL` | ❌ | `INFO` | Python log level |

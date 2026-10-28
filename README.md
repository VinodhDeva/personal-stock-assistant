# Personal AI Stock Market Assistant (India)

A local, free-tier decision-support app for NSE/BSE stocks: watchlist, delayed quotes, charts, technical indicators,
deterministic BUY/SELL/HOLD signals with full explanations, paper trading, backtests, Telegram alerts and a local-LLM
(Ollama) assistant.

> **Not investment advice. No real orders.** This version contains no order-placement code at all. Signals are
> outputs of example rules, not predictions. A BUY signal does not mean a price will rise.

## Quick start (local, no Docker)

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+. Optional: Ollama, a Telegram bot.

```bash
cp .env.example .env
```

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. API docs (OpenAPI): http://localhost:8000/docs.

Without `DATABASE_URL` the backend uses SQLite at `data/app.db`, so it runs with zero setup.

## Docker Compose (PostgreSQL)

Set `POSTGRES_PASSWORD` in `.env`, then:

```bash
docker compose up --build
```

Dashboard: http://localhost:8080 · API: http://localhost:8000. Migrations run on backend start.
Ollama stays on the host; the backend reaches it at `host.docker.internal:11434`.

## Tests

```bash
cd backend && uv run pytest && uv run ruff check app tests && uv run mypy app
```

```bash
cd frontend && npm test && npm run typecheck
```

All tests use mocked market data. No live API or credentials are needed.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite `data/app.db` | e.g. `postgresql+psycopg://user:pass@host:5432/db` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed frontend origins |
| `YAHOO_ENABLED` | `true` | Yahoo Finance via `yfinance` (no key) |
| `ALPHA_VANTAGE_API_KEY` | empty | Optional free key |
| `ALPHA_VANTAGE_DAILY_LIMIT` / `_PER_MINUTE_LIMIT` | `25` / `5` | Local hard caps, checked before every request |
| `REFRESH_INTERVAL_SECONDS` | `300` | Scheduler interval (min 60, also editable in Settings) |
| `MARKET_TIMEZONE`, `MARKET_OPEN`, `MARKET_CLOSE` | `Asia/Kolkata`, `09:15`, `15:30` | Market session |
| `STALE_AFTER_MINUTES` | `30` | Quote older than this during market hours = `stale` |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `http://localhost:11434`, `qwen3.5:9b` | Local LLM |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | Enables Telegram delivery |
| `NOTIFICATION_COOLDOWN_MINUTES` | `60` | Same alert key is not re-sent within this window |
| `PAPER_STARTING_CAPITAL` | `1000000` | Simulated INR capital |

Secrets are read only from the environment, never returned by the API, and masked in logs.

## Market data providers

| Provider | Key | Use | Freshness label |
|---|---|---|---|
| Yahoo Finance (`yfinance`) | none | Quotes, daily + limited intraday history, search | `delayed` (Yahoo does not guarantee real-time) |
| Alpha Vantage | free key | Daily history, end-of-day quote; BSE as `SYMBOL.BSE` (NSE coverage not guaranteed) | `delayed` / `historical` |
| CSV upload | none | Your own OHLCV for backtesting: `POST /api/stocks/{symbol}/csv` | `historical` |
| Broker API | — | Interface only (`providers/broker.py`), not implemented | — |

The backend logs provider capabilities at startup; `GET /api/providers/status` and the Settings page show them.
When one provider fails, the next one is tried **and the response names the provider used plus a fallback warning**.
When all fail, the last stored quote is returned labelled `cached` with its original timestamp.

**Freshness labels:** `live` is only shown when a provider confirms real-time data. None of the free providers do,
so you will not see `live` today. Refreshing more often cannot make data fresher than the provider publishes it.

Symbols: NSE `RELIANCE.NS`, BSE `RELIANCE.BO`. Typing `RELIANCE` with exchange NSE becomes `RELIANCE.NS`.

### Costs

Everything here is free: Yahoo (unofficial, may throttle or change without notice), Alpha Vantage free tier
(25 requests/day at time of writing), Telegram Bot API, Ollama. The only cost is your machine running Ollama.
A paid real-time feed can later be added as a new provider class without changing strategy or UI code.

## Strategy `ema_crossover_v1` (educational example)

Runs on **completed daily candles** (today's bar is excluded while the market is open).

- **Potential BUY:** EMA12 crosses above EMA26 on the latest completed bar, RSI(14) within `[45, 70]` and rising,
  close above SMA20, volume ≥ 1 × 20-day average. Not issued if a paper position is already open.
- **Potential SELL / exit:** EMA12 crosses below EMA26, or a paper position's stop-loss / take-profit is touched.
- **HOLD:** nothing triggered, fewer than 60 bars, indicators missing, provider down, or data `stale`.

Risk levels: stop = entry − 2 × ATR(14), take-profit = entry + 2 × (entry − stop). All thresholds are configurable
in Settings. Each signal stores: symbol, exchange, type, price, timestamps, freshness, provider, indicators, rules met,
rules not met, invalidation conditions, risk levels and strategy version.

Signals are deduplicated by `symbol|type|bar date|version` (DB unique key), so the same unchanged signal is stored
and notified once.

## Paper portfolio and risk

Average-cost accounting with fees, realized/unrealized P&L, exposure and max drawdown. Trades are rejected when they
would exceed cash, the max risk per trade (when a stop is given) or the max portfolio exposure. No short selling.
The scheduler closes simulated positions when the latest quote crosses their stop-loss or take-profit.
`POST /api/portfolio/position-size` suggests a share count from your risk budget.

## Backtesting

`GET /api/backtest/ema_crossover?symbol=TCS.NS&period=2y&cost_bps=10&slippage_bps=5`

- Decision at bar *t* uses only data up to *t*; orders fill at the **open of t+1**.
- Costs and slippage are charged on both sides; stops/targets are checked intrabar, stop first if both hit.
- Tests prove that altering future bars does not change earlier decisions (no look-ahead).
- Results are hypothetical and exclude taxes, liquidity limits and gaps beyond the open.

## AI assistant (Ollama)

```bash
ollama pull qwen3.5:9b
```

Any installed model works: set `OLLAMA_MODEL`. The backend sends the model only a JSON context of stored signals,
quotes with timestamps/freshness and strategy settings, with instructions to use nothing else. Every answer also
has a deterministic, template-built explanation; if Ollama is down, that is returned instead and everything else
keeps working. Requests to place trades are refused. No secrets or account data are sent.

## Telegram alerts

1. Message [@BotFather](https://t.me/BotFather), run `/newbot`, copy the token.
2. Send any message to your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
3. Put both in `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) and restart the backend.

Alerts: potential BUY/SELL (per-symbol toggle on the Watchlist page), price thresholds, paper stop-loss/take-profit
exits, provider errors and stale data. Each carries symbol, exchange, price, data timestamp, rationale, risk levels
and a dashboard link. Sends retry with backoff (429 `retry_after` respected); failures are logged. Without
Telegram, notifications go to the backend log and `GET /api/notifications`.

## Scheduler

One APScheduler job refreshes the whole watchlist (no per-stock loops) every `REFRESH_INTERVAL_SECONDS` during
market hours, plus one run 20 minutes after the close to evaluate the completed daily candle. Weekends and the
holidays in `data/market_holidays.json` are skipped. **That file only has fixed-date national holidays; add the
festival holidays from the NSE circular each year.** The job never overlaps itself; run one backend process only.
"Refresh data & signals" on the dashboard runs a cycle on demand.

## API

`GET /api/health` · `GET /api/providers/status` · `GET|POST /api/watchlist` · `PATCH|DELETE /api/watchlist/{symbol}` ·
`GET /api/stocks/search?q=` · `GET /api/stocks/{symbol}/quote|history|indicators` · `POST /api/stocks/{symbol}/csv` ·
`GET /api/signals` (filters, pagination) · `GET /api/signals/latest` · `GET /api/signals/{symbol}` ·
`POST /api/signals/refresh` · `POST /api/signals/{symbol}/evaluate` · `GET|POST /api/alerts` · `DELETE /api/alerts/{id}` ·
`GET /api/portfolio` · `POST /api/portfolio/paper-trades` · `GET /api/portfolio/trades` · `POST /api/portfolio/position-size` ·
`POST /api/assistant/chat` · `GET /api/backtest/{strategy_id}` · `GET /api/settings` · `PUT /api/settings/strategy|scheduler` ·
`GET /api/notifications`

Errors always look like `{"error": {"code", "message", "details"}}`.

## Limitations

- Free data is delayed and unofficial; Yahoo can throttle, change, or return gaps. Treat timestamps as authoritative.
- Daily-bar strategy only; intraday charts are not provided in the UI.
- Single-user, no authentication. Run it on your own machine only.
- Holidays file must be maintained by hand.
- Backtests are simplified (see above). Past results do not indicate future results.

Architecture details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Synthetic sample data for CSV import:
`data/samples/SAMPLE_synthetic_ohlcv.csv` (randomly generated, not real prices).

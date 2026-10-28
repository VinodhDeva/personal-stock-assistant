# Architecture

Decision-support tool for Indian equities. **Paper trading only. No real order placement exists in this codebase.**

```
                +--------------------------- backend (FastAPI, Python 3.12) ---------------------------+
React (Vite) -->| api/ ──> services/ ──> providers/ (yahoo | alpha_vantage | csv | broker stub)          |
 TanStack Query |            │      └──> indicators/ (pure pandas)  ──> strategies/ (deterministic rules) |
                |            │      └──> backtesting/ (bar-by-bar, no look-ahead)                         |
                |            │      └──> notifications/ (Telegram or local log, dedupe + cooldown)        |
                |            │      └──> assistant/ (Ollama; receives structured facts only)              |
                |            └──> db/ + models/ (SQLAlchemy, Alembic; PostgreSQL or SQLite)              |
                |  services/scheduler.py: ONE APScheduler job for the whole watchlist                 |
                +--------------------------------------------------------------------------------------+
```

## Layer rules

| Layer | Owns | Must not |
|---|---|---|
| `providers/` | Fetching, rate limiting, caching, retries, symbol mapping, freshness metadata | Compute signals |
| `indicators/` | RSI, SMA, EMA, MACD, ATR, avg volume, % change. Pure functions on DataFrames | Touch network or DB |
| `strategies/` | BUY/SELL/HOLD decisions with triggered rules, invalidation and risk levels | Call the LLM |
| `backtesting/` | Simulation with costs and slippage; decisions at bar *t* only use bars `<= t`, fills at *t+1* open | Use future rows |
| `assistant/` | Turning engine output into prose | Produce prices, indicators or signals; place trades |
| `notifications/` | Delivery, retry, cooldown, dedupe log | Decide what is a signal |

## Data freshness

Every quote and bar set carries `provider`, `data_timestamp`, `fetched_at` and `freshness`:

- `live` - only if the provider confirms real-time. **No configured free provider does, so this is never emitted today.**
- `delayed` - fresh response from a provider that does not guarantee real-time (Yahoo, Alpha Vantage).
- `cached` - served from cache or DB after a failed fetch. Shown with the original timestamp.
- `historical` - CSV uploads and end-of-day bars.
- `stale` - data older than `STALE_AFTER_MINUTES` during market hours. Strategy returns HOLD on stale data.

A scheduler that runs every minute cannot make data fresher than the provider publishes it.

## Signals

Strategy `ema_crossover_v1` runs on **completed daily candles** (today's bar is dropped while the market is open).
Each signal stores symbol, exchange, type, price, timestamps, freshness, indicators, rules triggered,
invalidation conditions, risk levels and strategy version. A `dedupe_key = symbol|type|bar_date|version`
is unique in the DB, so re-evaluating the same bar never creates or notifies twice.

## Duplicate-execution safety

The scheduler has one job (`max_instances=1`, `coalesce=True`) guarded by a process lock.
DB unique keys on signals and notification keys make an accidental second run harmless.
Run one backend process; multiple workers would each start a scheduler.

"""One job refreshes the whole watchlist. A minute-level schedule cannot make free data fresher than
the provider publishes it; it only re-checks sooner."""

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.core.config import get_settings
from app.core.market_hours import is_market_open, is_trading_day, now_market
from app.db.session import SessionLocal
from app.models import PriceAlert, WatchlistItem, utcnow
from app.notifications.notifier import Notifier, format_signal, get_notifier
from app.providers.base import Freshness, ProviderError
from app.providers.registry import ProviderRegistry, get_registry
from app.services import market, portfolio
from app.services.settings_store import get_refresh_interval, get_strategy_config
from app.services.signals import evaluate_symbol

log = logging.getLogger(__name__)
_cycle_lock = threading.Lock()
last_run: dict = {"started_at": None, "finished_at": None, "result": None}


def run_cycle(registry: ProviderRegistry | None = None, notifier: Notifier | None = None, force: bool = False) -> dict:
    """Quotes -> price alerts -> paper stop/target -> signals for all watchlist symbols."""
    if not _cycle_lock.acquire(blocking=False):
        return {"skipped": "previous cycle still running"}
    try:
        now = now_market()
        if not force and not is_market_open(now):
            return {"skipped": "market closed"}
        last_run["started_at"] = now.isoformat()
        result = _cycle(registry or get_registry(), notifier or get_notifier())
        last_run.update(finished_at=now_market().isoformat(), result=result)
        return result
    finally:
        _cycle_lock.release()


def _cycle(registry: ProviderRegistry, notifier: Notifier) -> dict:
    s = get_settings()
    stats = {"symbols": 0, "quotes": 0, "new_signals": 0, "alerts_triggered": 0, "paper_exits": 0, "errors": 0}
    with SessionLocal() as db:
        cfg = get_strategy_config(db)
        symbols = [w.symbol for w in db.scalars(select(WatchlistItem))]
        notify_for = {w.symbol for w in db.scalars(select(WatchlistItem).where(WatchlistItem.notify_signals))}
        led = portfolio.replay(portfolio.list_trades(db), s.paper_starting_capital)
        symbols_all = sorted(set(symbols) | set(led.positions))
        stats["symbols"] = len(symbols_all)
        quotes: dict[str, market.QuoteView] = {}
        for sym in symbols_all:
            try:
                q = market.get_quote(db, registry, sym)
                quotes[sym] = q
                stats["quotes"] += 1
                if q.freshness in (Freshness.STALE, Freshness.CACHED):
                    notifier.notify(
                        db,
                        f"stale|{sym}|{q.data_timestamp:%Y-%m-%d}",
                        "stale_data",
                        f"Data warning for {sym}: latest quote is {q.freshness} "
                        f"(timestamp {q.data_timestamp:%Y-%m-%d %H:%M %Z}, via {q.provider}).",
                    )
            except ProviderError as e:
                stats["errors"] += 1
                notifier.notify(
                    db, f"provider_error|{sym}", "provider_error", f"Market data unavailable for {sym}: {e}"
                )

        # price alerts (one-shot)
        for a in db.scalars(select(PriceAlert).where(PriceAlert.active)):
            aq = quotes.get(a.symbol)
            if not aq or aq.freshness == Freshness.STALE:
                continue
            if (a.condition == "above" and aq.price >= a.price) or (a.condition == "below" and aq.price <= a.price):
                a.active, a.triggered_at, a.triggered_price = False, utcnow(), aq.price
                db.commit()
                stats["alerts_triggered"] += 1
                notifier.notify(
                    db,
                    f"alert|{a.id}",
                    "price_alert",
                    f"Price alert: {a.symbol} is {a.condition} {a.price:,.2f} "
                    f"(price {aq.price:,.2f}, {aq.freshness}, data {aq.data_timestamp:%Y-%m-%d %H:%M %Z}, "
                    f"via {aq.provider})\n{s.dashboard_url}/stocks/{a.symbol}",
                )

        # simulated stop-loss / take-profit
        for sym, pos in list(led.positions.items()):
            pq = quotes.get(sym)
            if not pq or pq.freshness == Freshness.STALE:
                continue
            hit = (
                ("stop-loss", pos.stop_loss)
                if pos.stop_loss and pq.price <= pos.stop_loss
                else ("take-profit", pos.take_profit)
                if pos.take_profit and pq.price >= pos.take_profit
                else None
            )
            if hit:
                t = portfolio.record_trade(
                    db,
                    starting_capital=s.paper_starting_capital,
                    symbol=sym,
                    side="SELL",
                    quantity=pos.quantity,
                    price=pq.price,
                    reason=f"simulated {hit[0]}",
                    price_source=f"{pq.provider}/{pq.freshness}",
                )
                stats["paper_exits"] += 1
                notifier.notify(
                    db,
                    f"paper_exit|{t.id}",
                    "paper_exit",
                    f"Paper {hit[0]} hit: sold {pos.quantity:g} {sym} at {pq.price:,.2f} "
                    f"(level {hit[1]:,.2f}). Realized P&L {t.realized_pnl:,.2f}. Simulation only.",
                )

        for sym in symbols:
            ev = evaluate_symbol(db, registry, sym, cfg, s.paper_starting_capital)
            if ev.is_new:
                stats["new_signals"] += 1
                if ev.signal.signal_type != "HOLD" and sym in notify_for:
                    notifier.notify(db, ev.signal.dedupe_key, "signal", format_signal(ev.signal, s.dashboard_url))
    log.info("market cycle done: %s", stats)
    return stats


_scheduler: BackgroundScheduler | None = None


def _post_close() -> None:
    if is_trading_day(now_market().date()):
        run_cycle(force=True)


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    s = get_settings()
    with SessionLocal() as db:
        interval = get_refresh_interval(db)
    sched = BackgroundScheduler(timezone=s.market_timezone)
    sched.add_job(run_cycle, "interval", seconds=interval, id="market_cycle", max_instances=1, coalesce=True)
    # After the close the daily candle is complete: evaluate it once.
    sched.add_job(
        _post_close,
        CronTrigger(
            day_of_week="mon-fri",
            hour=s.market_close.hour,
            minute=min(59, s.market_close.minute + 20),
            timezone=s.market_timezone,
        ),
        id="post_close",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    log.info(
        "scheduler started: every %ss within market hours (%s-%s %s)",
        interval,
        s.market_open,
        s.market_close,
        s.market_timezone,
    )
    return sched


def reschedule(seconds: int) -> None:
    if _scheduler:
        _scheduler.reschedule_job("market_cycle", trigger="interval", seconds=seconds)

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.market_hours import is_market_open, is_trading_day, market_tz, now_market
from app.models import MarketSnapshot
from app.providers.base import Bars, Freshness, ProviderError, Quote, exchange_of
from app.providers.registry import ProviderRegistry

log = logging.getLogger(__name__)


def last_session_date(now: datetime) -> date:
    """Most recent trading day whose session has started."""
    d = now.date()
    return d if is_trading_day(d) and now.time() >= get_settings().market_open else previous_trading_day(d)


def previous_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def classify(
    provider_freshness: Freshness, data_ts: datetime | None, now: datetime | None = None, daily: bool = False
) -> Freshness:
    """Downgrades to STALE when the data is older than the market situation allows."""
    if data_ts is None:
        return Freshness.STALE
    if provider_freshness == Freshness.HISTORICAL:
        return Freshness.HISTORICAL
    now = now or now_market()
    if daily:
        # Daily bars: the latest *completed* session must be present.
        expected = previous_trading_day(now.date()) if is_market_open(now) else last_session_date(now)
        return Freshness.STALE if data_ts.astimezone(market_tz()).date() < expected else provider_freshness
    if is_market_open(now):
        if now - data_ts > timedelta(minutes=get_settings().stale_after_minutes):
            return Freshness.STALE
    elif data_ts.astimezone(market_tz()).date() < last_session_date(now):
        return Freshness.STALE
    return provider_freshness


@dataclass
class QuoteView:
    symbol: str
    exchange: str
    price: float
    previous_close: float | None
    change_pct: float | None
    data_timestamp: datetime
    fetched_at: datetime
    provider: str
    freshness: Freshness
    warnings: list[str] = field(default_factory=list)


def _view(q: Quote, warnings: list[str]) -> QuoteView:
    return QuoteView(
        q.symbol,
        exchange_of(q.symbol),
        q.price,
        q.previous_close,
        q.change_pct,
        q.data_timestamp,
        q.fetched_at,
        q.provider,
        classify(q.freshness, q.data_timestamp),
        warnings,
    )


def get_quote(db: Session, registry: ProviderRegistry, symbol: str) -> QuoteView:
    try:
        q, notes = registry.get_quote(symbol)
    except ProviderError as e:
        snap = db.scalars(
            select(MarketSnapshot).where(MarketSnapshot.symbol == symbol).order_by(MarketSnapshot.id.desc())
        ).first()
        if not snap:
            raise
        # Explicitly labelled cache: never presented as fresh.
        return QuoteView(
            symbol,
            exchange_of(symbol),
            snap.price,
            snap.previous_close,
            (snap.price - snap.previous_close) / snap.previous_close * 100 if snap.previous_close else None,
            snap.data_timestamp,
            snap.fetched_at,
            snap.provider,
            Freshness.CACHED,
            [f"providers failed, showing last stored quote: {e}"],
        )
    if q.freshness != Freshness.CACHED:
        db.add(
            MarketSnapshot(
                symbol=symbol,
                price=q.price,
                previous_close=q.previous_close,
                provider=q.provider,
                freshness=q.freshness.value,
                data_timestamp=q.data_timestamp,
                fetched_at=q.fetched_at,
            )
        )
        db.commit()
    return _view(q, [f"fallback used: {n}" for n in notes])


def get_history(
    registry: ProviderRegistry, symbol: str, period: str = "1y", interval: str = "1d", provider: str | None = None
) -> tuple[Bars, Freshness, list[str]]:
    bars, notes = registry.get_history(symbol, period, interval, provider)
    return (
        bars,
        classify(bars.freshness, bars.data_timestamp, daily=interval == "1d"),
        [f"fallback used: {n}" for n in notes],
    )

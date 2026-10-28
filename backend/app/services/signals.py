import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.market_hours import is_market_open, now_market
from app.models import Signal
from app.providers.base import Freshness, ProviderError, exchange_of
from app.providers.registry import ProviderRegistry
from app.services import market
from app.services.portfolio import list_trades, replay
from app.strategies.ema_crossover import (
    Position,
    SignalResult,
    SignalType,
    StrategyConfig,
    completed_bars,
    evaluate,
)

log = logging.getLogger(__name__)


@dataclass
class Evaluation:
    signal: Signal
    is_new: bool


def dedupe_key(symbol: str, result: SignalResult) -> str:
    bar = result.bar_timestamp.date().isoformat() if result.bar_timestamp else "nodata"
    return f"{symbol}|{result.signal_type}|{bar}|{result.strategy_version}"


def evaluate_symbol(
    db: Session, registry: ProviderRegistry, symbol: str, cfg: StrategyConfig, starting_capital: float
) -> Evaluation:
    now = now_market()
    provider, freshness = None, Freshness.STALE
    try:
        bars, freshness, _ = market.get_history(registry, symbol, "1y", "1d")
        provider = bars.provider
        df = completed_bars(bars.df, now, is_market_open(now))
    except ProviderError as e:
        log.warning("history unavailable for %s: %s", symbol, e)
        df = None

    led = replay(list_trades(db), starting_capital)
    p = led.positions.get(symbol)
    position = Position(p.quantity, p.avg_price, p.stop_loss, p.take_profit) if p else None

    if df is None:
        result = SignalResult(
            SignalType.HOLD, None, None, {}, [], ["market data unavailable from all providers"], [], {}
        )
    else:
        result = evaluate(df, cfg, position)
        if freshness == Freshness.STALE and result.signal_type != SignalType.HOLD:
            result = SignalResult(
                SignalType.HOLD,
                result.price,
                result.bar_timestamp,
                result.indicators,
                [],
                [f"data is stale; a {result.signal_type} would have been suggested but stale data is not acted on"],
                [],
                result.risk,
            )

    key = dedupe_key(symbol, result)
    existing = db.scalars(select(Signal).where(Signal.dedupe_key == key)).first()
    if existing:
        return Evaluation(existing, False)
    sig = Signal(
        dedupe_key=key,
        symbol=symbol,
        exchange=exchange_of(symbol),
        signal_type=result.signal_type.value,
        price=result.price,
        data_timestamp=result.bar_timestamp,
        freshness=freshness.value,
        provider=provider,
        indicators=result.indicators,
        rules_triggered=result.rules_triggered,
        rules_failed=result.rules_failed,
        invalidation=result.invalidation,
        risk=result.risk,
        strategy_version=result.strategy_version,
    )
    db.add(sig)
    try:
        db.commit()
    except IntegrityError:  # a concurrent run stored the same key first
        db.rollback()
        return Evaluation(db.scalars(select(Signal).where(Signal.dedupe_key == key)).one(), False)
    return Evaluation(sig, True)

from app.core.errors import AppError
from app.providers.base import normalize_symbol


def symbol_param(symbol: str, exchange: str | None = None) -> str:
    try:
        return normalize_symbol(symbol, exchange)
    except ValueError as e:
        raise AppError(422, "invalid_symbol", str(e)) from None


def serialize_signal(s) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": s.id,
        "symbol": s.symbol,
        "exchange": s.exchange,
        "signal_type": s.signal_type,
        "price": s.price,
        "signal_timestamp": s.signal_timestamp,
        "data_timestamp": s.data_timestamp,
        "freshness": s.freshness,
        "provider": s.provider,
        "indicators": s.indicators,
        "rules_triggered": s.rules_triggered,
        "rules_failed": s.rules_failed,
        "invalidation": s.invalidation,
        "risk": s.risk,
        "strategy_version": s.strategy_version,
    }


def page(items: list, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}

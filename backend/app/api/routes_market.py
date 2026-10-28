import csv
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import page, serialize_signal, symbol_param
from app.core.config import DATA_DIR, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.indicators.core import compute_all
from app.models import PriceAlert, Signal, WatchlistItem
from app.providers.base import ProviderError, SymbolNotFound, exchange_of
from app.providers.csv_provider import CSVProvider, CSVValidationError
from app.providers.registry import get_registry
from app.schemas import AlertCreate, WatchlistCreate, WatchlistUpdate
from app.services import market
from app.services.scheduler import run_cycle
from app.services.settings_store import get_strategy_config
from app.services.signals import evaluate_symbol

router = APIRouter(prefix="/api")
Period = Literal["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
Interval = Literal["1d", "1h", "15m", "5m", "1m"]


def provider_error(e: ProviderError) -> AppError:
    if isinstance(e, SymbolNotFound):
        return AppError(404, "symbol_not_found", str(e))
    return AppError(503, "provider_unavailable", str(e))


# ---------- watchlist ----------
@router.get("/watchlist", tags=["watchlist"])
def list_watchlist(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol))
    return [
        {
            "symbol": w.symbol,
            "exchange": w.exchange,
            "name": w.name,
            "notify_signals": w.notify_signals,
            "created_at": w.created_at,
        }
        for w in rows
    ]


@router.post("/watchlist", status_code=201, tags=["watchlist"])
def add_watchlist(body: WatchlistCreate, db: Session = Depends(get_db)) -> dict:
    symbol = symbol_param(body.symbol, body.exchange)
    if db.scalars(select(WatchlistItem).where(WatchlistItem.symbol == symbol)).first():
        raise AppError(409, "already_exists", f"{symbol} is already in the watchlist")
    warning = None
    if body.validate_symbol:
        try:
            get_registry().get_history(symbol, "1mo", "1d")
        except SymbolNotFound:
            raise AppError(404, "symbol_not_found", f"no market data found for {symbol}") from None
        except ProviderError as e:
            warning = f"could not validate symbol now ({e}); added anyway"
    item = WatchlistItem(
        symbol=symbol,
        exchange=exchange_of(symbol),
        name=body.name or lookup_name(symbol),
        notify_signals=body.notify_signals,
    )
    db.add(item)
    db.commit()
    return {
        "symbol": item.symbol,
        "exchange": item.exchange,
        "name": item.name,
        "notify_signals": item.notify_signals,
        "warning": warning,
    }


@router.patch("/watchlist/{symbol}", tags=["watchlist"])
def update_watchlist(symbol: str, body: WatchlistUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.scalars(select(WatchlistItem).where(WatchlistItem.symbol == symbol_param(symbol))).first()
    if not item:
        raise AppError(404, "not_found", "symbol not in watchlist")
    item.notify_signals = body.notify_signals
    db.commit()
    return {"symbol": item.symbol, "notify_signals": item.notify_signals}


@router.delete("/watchlist/{symbol}", status_code=204, tags=["watchlist"])
def remove_watchlist(symbol: str, db: Session = Depends(get_db)) -> None:
    item = db.scalars(select(WatchlistItem).where(WatchlistItem.symbol == symbol_param(symbol))).first()
    if not item:
        raise AppError(404, "not_found", "symbol not in watchlist")
    db.delete(item)
    db.commit()


# ---------- stocks ----------
def _local_symbols() -> list[dict]:
    path = DATA_DIR / "samples" / "nse_symbols.csv"
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def lookup_name(symbol: str) -> str | None:
    return next((r["name"] for r in _local_symbols() if r["symbol"] == symbol), None)


@router.get("/stocks/search", tags=["stocks"])
def search(q: str = Query(min_length=1, max_length=40), remote: bool = False) -> list[dict]:
    ql = q.lower()
    hits = [r for r in _local_symbols() if ql in r["symbol"].lower() or ql in r["name"].lower()][:15]
    if remote or not hits:
        yahoo = get_registry().providers.get("yahoo")
        if yahoo and yahoo.is_configured():
            seen = {h["symbol"] for h in hits}
            hits += [r for r in yahoo.search(q) if r["symbol"] not in seen]  # type: ignore[attr-defined]
    return [{**h, "exchange": exchange_of(h["symbol"])} for h in hits]


@router.get("/stocks/{symbol}/quote", tags=["stocks"])
def quote(symbol: str, db: Session = Depends(get_db)) -> dict:
    try:
        return asdict(market.get_quote(db, get_registry(), symbol_param(symbol)))
    except ProviderError as e:
        raise provider_error(e) from None


def _history(symbol: str, period: str, interval: str, provider: str | None):  # type: ignore[no-untyped-def]
    if provider and provider not in get_registry().providers:
        raise AppError(422, "invalid_provider", f"unknown provider {provider}")
    try:
        return market.get_history(get_registry(), symbol_param(symbol), period, interval, provider)
    except ProviderError as e:
        raise provider_error(e) from None


def _meta(bars, freshness, warnings) -> dict:  # type: ignore[no-untyped-def]
    return {
        "symbol": bars.symbol,
        "exchange": exchange_of(bars.symbol),
        "provider": bars.provider,
        "interval": bars.interval,
        "freshness": freshness,
        "data_timestamp": bars.data_timestamp,
        "fetched_at": bars.fetched_at,
        "warnings": warnings,
    }


@router.get("/stocks/{symbol}/history", tags=["stocks"])
def history(symbol: str, period: Period = "1y", interval: Interval = "1d", provider: str | None = None) -> dict:
    bars, freshness, warnings = _history(symbol, period, interval, provider)
    df = bars.df
    candles = [
        {
            "time": int(ts.timestamp()),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for ts, r in zip(df.index, df.itertuples(), strict=True)
    ]
    return {**_meta(bars, freshness, warnings), "candles": candles}


@router.get("/stocks/{symbol}/indicators", tags=["stocks"])
def indicators(symbol: str, period: Period = "1y", provider: str | None = None) -> dict:
    bars, freshness, warnings = _history(symbol, period, "1d", provider)
    ind = compute_all(bars.df)
    cols = [
        "close",
        "rsi_14",
        "sma_20",
        "sma_50",
        "ema_12",
        "ema_26",
        "macd",
        "macd_signal",
        "macd_hist",
        "avg_volume_20",
        "atr_14",
        "pct_change",
    ]
    clean = ind[cols].astype(object).where(ind[cols].notna(), None)
    series = [
        {"time": int(ts.timestamp()), **{c: (None if v is None else round(float(v), 4)) for c, v in row.items()}}
        for ts, row in zip(clean.index, clean.to_dict("records"), strict=True)
    ]
    return {**_meta(bars, freshness, warnings), "latest": series[-1] if series else None, "series": series}


@router.post("/stocks/{symbol}/csv", status_code=201, tags=["stocks"])
async def upload_csv(symbol: str, file: UploadFile) -> dict:
    sym = symbol_param(symbol)
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise AppError(413, "file_too_large", f"max {get_settings().max_upload_bytes // 1024 // 1024} MB")
    csv_provider = get_registry().providers["csv"]
    assert isinstance(csv_provider, CSVProvider)
    try:
        df = csv_provider.save(sym, content)
    except CSVValidationError as e:
        raise AppError(422, "invalid_csv", str(e)) from None
    return {
        "symbol": sym,
        "rows": len(df),
        "start": df.index[0],
        "end": df.index[-1],
        "provider": "csv",
        "freshness": "historical",
    }


# ---------- signals ----------
@router.get("/signals", tags=["signals"])
def list_signals(
    symbol: str | None = None,
    signal_type: Literal["BUY", "SELL", "HOLD"] | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    q = select(Signal)
    if symbol:
        q = q.where(Signal.symbol == symbol_param(symbol))
    if signal_type:
        q = q.where(Signal.signal_type == signal_type)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Signal.signal_timestamp.desc(), Signal.id.desc()).limit(limit).offset(offset))
    return page([serialize_signal(s) for s in rows], total, limit, offset)


@router.get("/signals/latest", tags=["signals"])
def latest_signals(db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for w in db.scalars(select(WatchlistItem).order_by(WatchlistItem.symbol)):
        s = db.scalars(select(Signal).where(Signal.symbol == w.symbol).order_by(Signal.id.desc())).first()
        if s:
            out.append(serialize_signal(s))
    return out


@router.post("/signals/refresh", tags=["signals"])
def refresh_signals() -> dict:
    """Runs one full cycle now (quotes, alerts, paper stops, signals), regardless of market hours."""
    return run_cycle(force=True)


@router.post("/signals/{symbol}/evaluate", tags=["signals"])
def evaluate_now(symbol: str, db: Session = Depends(get_db)) -> dict:
    ev = evaluate_symbol(
        db, get_registry(), symbol_param(symbol), get_strategy_config(db), get_settings().paper_starting_capital
    )
    return {**serialize_signal(ev.signal), "is_new": ev.is_new}


@router.get("/signals/{symbol}", tags=["signals"])
def signals_for(
    symbol: str, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)
) -> dict:
    return list_signals(symbol=symbol, signal_type=None, limit=limit, offset=offset, db=db)


# ---------- alerts ----------
def _alert(a: PriceAlert) -> dict:
    return {
        "id": a.id,
        "symbol": a.symbol,
        "condition": a.condition,
        "price": a.price,
        "active": a.active,
        "note": a.note,
        "created_at": a.created_at,
        "triggered_at": a.triggered_at,
        "triggered_price": a.triggered_price,
    }


@router.post("/alerts", status_code=201, tags=["alerts"])
def create_alert(body: AlertCreate, db: Session = Depends(get_db)) -> dict:
    a = PriceAlert(symbol=symbol_param(body.symbol), condition=body.condition, price=body.price, note=body.note)
    db.add(a)
    db.commit()
    return _alert(a)


@router.get("/alerts", tags=["alerts"])
def list_alerts(symbol: str | None = None, active: bool | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = select(PriceAlert).order_by(PriceAlert.id.desc())
    if symbol:
        q = q.where(PriceAlert.symbol == symbol_param(symbol))
    if active is not None:
        q = q.where(PriceAlert.active == active)
    return [_alert(a) for a in db.scalars(q.limit(500))]


@router.delete("/alerts/{alert_id}", status_code=204, tags=["alerts"])
def delete_alert(alert_id: int, db: Session = Depends(get_db)) -> None:
    a = db.get(PriceAlert, alert_id)
    if not a:
        raise AppError(404, "not_found", "alert not found")
    db.delete(a)
    db.commit()

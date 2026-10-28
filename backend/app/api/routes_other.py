from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import page, serialize_signal, symbol_param
from app.assistant.ollama import OllamaClient
from app.assistant.service import answer, detect_symbols
from app.backtesting.engine import run_backtest
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.market_hours import is_market_open, now_market
from app.db.session import get_db
from app.models import NotificationLog, PaperTrade, Signal, WatchlistItem
from app.providers.base import ProviderError
from app.providers.registry import get_registry
from app.schemas import ChatRequest, PaperTradeCreate, PositionSizeRequest, SchedulerSettings
from app.services import market, portfolio
from app.services.scheduler import last_run, reschedule
from app.services.settings_store import (
    get_refresh_interval,
    get_strategy_config,
    set_refresh_interval,
    set_strategy_config,
)
from app.strategies.ema_crossover import STRATEGY_ID, STRATEGY_VERSION, StrategyConfig

router = APIRouter(prefix="/api")


def ollama() -> OllamaClient:
    s = get_settings()
    return OllamaClient(s.ollama_base_url, s.ollama_model, s.ollama_timeout_seconds)


# ---------- system ----------
@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(select(1))
    now = now_market()
    return {"status": "ok", "market_time": now, "market_open": is_market_open(now), "real_orders": False}


@router.get("/providers/status", tags=["system"])
def providers_status() -> dict:
    s = get_settings()
    return {
        "providers": get_registry().status(),
        "live_data_available": False,
        "note": "No configured free provider confirms real-time data. Quotes are labelled delayed, cached, "
        "historical or stale. Refreshing more often cannot make data fresher than the provider.",
        "ollama": ollama().status(),
        "telegram": {
            "configured": s.telegram_configured,
            "help": None
            if s.telegram_configured
            else "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env and restart. Until then, "
            "notifications are written to the backend log and the notification history.",
        },
        "scheduler": {
            "enabled": s.scheduler_enabled,
            "market_timezone": s.market_timezone,
            "market_open": s.market_open,
            "market_close": s.market_close,
            "last_run": last_run,
        },
    }


@router.get("/settings", tags=["system"])
def get_app_settings(db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    return {
        "strategy": get_strategy_config(db).model_dump(),
        "strategy_schema": StrategyConfig.model_json_schema(),
        "refresh_interval_seconds": get_refresh_interval(db),
        "stale_after_minutes": s.stale_after_minutes,
        "paper_starting_capital": s.paper_starting_capital,
        "notification_cooldown_minutes": s.notification_cooldown_minutes,
        "ollama_model": s.ollama_model,
    }


@router.put("/settings/strategy", tags=["system"])
def put_strategy(cfg: StrategyConfig, db: Session = Depends(get_db)) -> dict:
    if cfg.rsi_buy_min >= cfg.rsi_buy_max:
        raise AppError(422, "invalid_thresholds", "rsi_buy_min must be below rsi_buy_max")
    return set_strategy_config(db, cfg).model_dump()


@router.put("/settings/scheduler", tags=["system"])
def put_scheduler(body: SchedulerSettings, db: Session = Depends(get_db)) -> dict:
    set_refresh_interval(db, body.refresh_interval_seconds)
    reschedule(body.refresh_interval_seconds)
    return body.model_dump()


@router.get("/notifications", tags=["system"])
def notifications(
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)
) -> dict:
    total = db.scalar(select(func.count(NotificationLog.id))) or 0
    rows = db.scalars(select(NotificationLog).order_by(NotificationLog.id.desc()).limit(limit).offset(offset))
    return page(
        [
            {
                "id": n.id,
                "kind": n.kind,
                "channel": n.channel,
                "status": n.status,
                "message": n.message,
                "error": n.error,
                "created_at": n.created_at,
            }
            for n in rows
        ],
        total,
        limit,
        offset,
    )


# ---------- portfolio ----------
def _marks(db: Session, symbols: list[str]) -> tuple[dict[str, float], dict[str, dict]]:
    marks, meta = {}, {}
    for s in symbols:
        try:
            q = market.get_quote(db, get_registry(), s)
            marks[s] = q.price
            meta[s] = {"provider": q.provider, "freshness": q.freshness, "data_timestamp": q.data_timestamp}
        except ProviderError as e:
            meta[s] = {"error": str(e)}
    return marks, meta


@router.get("/portfolio", tags=["portfolio"])
def get_portfolio(db: Session = Depends(get_db)) -> dict:
    cap = get_settings().paper_starting_capital
    led = portfolio.replay(portfolio.list_trades(db), cap)
    marks, meta = _marks(db, list(led.positions))
    out = portfolio.summary(db, cap, marks)
    for p in out["positions"]:
        p["price_meta"] = meta.get(p["symbol"])
    out["simulated"] = True
    return out


@router.post("/portfolio/paper-trades", status_code=201, tags=["portfolio"])
def create_paper_trade(body: PaperTradeCreate, db: Session = Depends(get_db)) -> dict:
    sym = symbol_param(body.symbol)
    price, source = body.price, "manual"
    if price is None:
        try:
            q = market.get_quote(db, get_registry(), sym)
        except ProviderError as e:
            raise AppError(503, "price_unavailable", f"no price available, enter one manually ({e})") from None
        price, source = q.price, f"{q.provider}/{q.freshness}@{q.data_timestamp.isoformat()}"
    cfg = get_strategy_config(db)
    cap = get_settings().paper_starting_capital
    led = portfolio.replay(portfolio.list_trades(db), cap)
    marks, _ = _marks(db, list(led.positions)) if body.side == "BUY" and body.enforce_risk_limits else ({}, {})
    t = portfolio.record_trade(
        db,
        starting_capital=cap,
        symbol=sym,
        side=body.side,
        quantity=body.quantity,
        price=price,
        fees=body.fees,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        reason=body.reason,
        price_source=source,
        risk_pct=cfg.max_risk_per_trade_pct if body.enforce_risk_limits else None,
        max_exposure_pct=cfg.max_portfolio_exposure_pct if body.enforce_risk_limits else None,
        marks=marks,
    )
    return _trade(t)


def _trade(t: PaperTrade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "side": t.side,
        "quantity": t.quantity,
        "price": t.price,
        "fees": t.fees,
        "stop_loss": t.stop_loss,
        "take_profit": t.take_profit,
        "realized_pnl": t.realized_pnl,
        "reason": t.reason,
        "price_source": t.price_source,
        "executed_at": t.executed_at,
    }


@router.get("/portfolio/trades", tags=["portfolio"])
def trades(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count(PaperTrade.id))) or 0
    rows = db.scalars(select(PaperTrade).order_by(PaperTrade.id.desc()).limit(limit).offset(offset))
    return page([_trade(t) for t in rows], total, limit, offset)


@router.post("/portfolio/position-size", tags=["portfolio"])
def size(body: PositionSizeRequest, db: Session = Depends(get_db)) -> dict:
    cfg = get_strategy_config(db)
    cap = get_settings().paper_starting_capital
    led = portfolio.replay(portfolio.list_trades(db), cap)
    exposure = sum(p.quantity * p.avg_price for p in led.positions.values())
    if body.stop_loss is not None and body.stop_loss >= body.entry:
        raise AppError(422, "invalid_stop", "stop-loss must be below entry")
    return portfolio.position_size(
        led.cash + exposure,
        led.cash,
        body.entry,
        body.stop_loss,
        cfg.max_risk_per_trade_pct,
        cfg.max_portfolio_exposure_pct,
        exposure,
    )


# ---------- assistant ----------
def build_context(db: Session, symbols: list[str]) -> dict:
    """Structured, secret-free facts for the LLM. Prices come from stored engine output and providers."""
    sigs, quotes = [], []
    for sym in symbols:
        s = db.scalars(select(Signal).where(Signal.symbol == sym).order_by(Signal.id.desc())).first()
        if s:
            d = serialize_signal(s)
            d.pop("id")
            sigs.append(d)
        try:
            q = market.get_quote(db, get_registry(), sym)
            quotes.append(
                {
                    "symbol": sym,
                    "price": q.price,
                    "change_pct": q.change_pct,
                    "data_timestamp": q.data_timestamp,
                    "freshness": q.freshness,
                    "provider": q.provider,
                }
            )
        except ProviderError as e:
            quotes.append({"symbol": sym, "error": str(e)})
    cfg = get_strategy_config(db).model_dump()
    return {
        "as_of": now_market(),
        "strategy": {"id": STRATEGY_ID, "version": STRATEGY_VERSION, "config": cfg},
        "signals": sigs,
        "quotes": quotes,
        "data_note": "No provider confirms live data; respect each freshness label.",
    }


@router.post("/assistant/chat", tags=["assistant"])
def chat(body: ChatRequest, db: Session = Depends(get_db)) -> dict:
    watch = [w.symbol for w in db.scalars(select(WatchlistItem))]
    symbols = [symbol_param(body.symbol)] if body.symbol else detect_symbols(body.message, watch) or watch
    client = ollama()
    return answer(body.message, build_context(db, symbols[:15]), client)


# ---------- backtest ----------
@router.get("/backtest/{strategy_id}", tags=["backtest"])
def backtest(
    strategy_id: str,
    symbol: str,
    period: str = Query("2y", pattern="^(1y|2y|5y|max)$"),
    provider: str | None = None,
    cost_bps: float = Query(10, ge=0, le=200),
    slippage_bps: float = Query(5, ge=0, le=200),
    db: Session = Depends(get_db),
) -> dict:
    if strategy_id not in (STRATEGY_ID, STRATEGY_VERSION):
        raise AppError(404, "unknown_strategy", f"available: {STRATEGY_ID}")
    sym = symbol_param(symbol)
    try:
        bars, freshness, warnings = market.get_history(get_registry(), sym, period, "1d", provider)
    except ProviderError as e:
        raise AppError(503, "provider_unavailable", str(e)) from None
    result = run_backtest(
        bars.df, get_strategy_config(db), get_settings().paper_starting_capital, cost_bps, slippage_bps
    )
    return {"symbol": sym, "provider": bars.provider, "freshness": freshness, "warnings": warnings, **result}

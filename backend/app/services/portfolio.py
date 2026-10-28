"""Paper portfolio accounting (average-cost method). Simulation only: no broker, no real orders."""

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import PaperTrade


@dataclass
class PositionState:
    symbol: str
    quantity: float
    avg_price: float
    stop_loss: float | None
    take_profit: float | None


@dataclass
class Ledger:
    cash: float
    realized_pnl: float
    fees: float
    positions: dict[str, PositionState]


def replay(trades: list[PaperTrade], starting_capital: float) -> Ledger:
    led = Ledger(starting_capital, 0.0, 0.0, {})
    for t in trades:
        apply(led, t.symbol, t.side, t.quantity, t.price, t.fees, t.stop_loss, t.take_profit)
    return led


def apply(
    led: Ledger,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    fees: float,
    stop: float | None = None,
    target: float | None = None,
) -> float | None:
    """Mutates the ledger; returns realized P&L for sells."""
    pos = led.positions.get(symbol)
    led.fees += fees
    if side == "BUY":
        cost = qty * price
        if pos:
            pos.avg_price = (pos.avg_price * pos.quantity + cost) / (pos.quantity + qty)
            pos.quantity += qty
            pos.stop_loss, pos.take_profit = stop or pos.stop_loss, target or pos.take_profit
        else:
            led.positions[symbol] = PositionState(symbol, qty, price, stop, target)
        led.cash -= cost + fees
        return None
    assert pos and pos.quantity >= qty - 1e-9, "sell exceeds position"
    pnl = (price - pos.avg_price) * qty - fees
    led.cash += qty * price - fees
    led.realized_pnl += pnl
    pos.quantity -= qty
    if pos.quantity <= 1e-9:
        del led.positions[symbol]
    return pnl


def position_size(
    equity: float,
    cash: float,
    entry: float,
    stop: float | None,
    risk_pct: float,
    max_exposure_pct: float,
    current_exposure: float,
) -> dict:
    """Shares such that (entry - stop) x shares <= risk_pct of equity, capped by exposure and cash."""
    if entry <= 0:
        raise ValueError("entry must be positive")
    risk_budget = equity * risk_pct / 100
    by_risk = math.floor(risk_budget / (entry - stop)) if stop and stop < entry else None
    exposure_room = max(0.0, equity * max_exposure_pct / 100 - current_exposure)
    by_exposure = math.floor(exposure_room / entry)
    by_cash = math.floor(max(cash, 0) / entry)
    qty = max(0, min(x for x in (by_risk, by_exposure, by_cash) if x is not None))
    return {
        "quantity": qty,
        "risk_budget": round(risk_budget, 2),
        "limit_by_risk": by_risk,
        "limit_by_exposure": by_exposure,
        "limit_by_cash": by_cash,
        "risk_amount": round(qty * (entry - stop), 2) if stop and stop < entry else None,
    }


def list_trades(db: Session) -> list[PaperTrade]:
    return list(db.scalars(select(PaperTrade).order_by(PaperTrade.executed_at, PaperTrade.id)))


def record_trade(
    db: Session,
    *,
    starting_capital: float,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    fees: float = 0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    reason: str | None = None,
    price_source: str | None = None,
    risk_pct: float | None = None,
    max_exposure_pct: float | None = None,
    marks: dict[str, float] | None = None,
) -> PaperTrade:
    led = replay(list_trades(db), starting_capital)
    pos = led.positions.get(symbol)
    if side == "SELL":
        if not pos or pos.quantity < quantity - 1e-9:
            raise AppError(
                422,
                "insufficient_position",
                f"cannot sell {quantity} {symbol}: holding "
                f"{pos.quantity if pos else 0} (short selling is not simulated)",
            )
    else:
        if quantity * price + fees > led.cash + 1e-6:
            raise AppError(422, "insufficient_cash", f"needs {quantity * price + fees:,.2f}, cash {led.cash:,.2f}")
        if stop_loss is not None and stop_loss >= price:
            raise AppError(422, "invalid_stop", "stop-loss must be below the entry price for a long position")
        if take_profit is not None and take_profit <= price:
            raise AppError(422, "invalid_target", "take-profit must be above the entry price")
        marks = marks or {}
        exposure = sum(p.quantity * marks.get(s, p.avg_price) for s, p in led.positions.items())
        equity = led.cash + exposure
        if max_exposure_pct is not None and exposure + quantity * price > equity * max_exposure_pct / 100 + 1e-6:
            raise AppError(422, "exposure_limit", f"trade would exceed max portfolio exposure {max_exposure_pct}%")
        if risk_pct is not None and stop_loss is not None:
            risk = quantity * (price - stop_loss)
            if risk > equity * risk_pct / 100 + 1e-6:
                raise AppError(
                    422,
                    "risk_limit",
                    f"risk {risk:,.2f} exceeds {risk_pct}% of equity ({equity * risk_pct / 100:,.2f})",
                )
    pnl = apply(led, symbol, side, quantity, price, fees, stop_loss, take_profit)
    trade = PaperTrade(
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        stop_loss=stop_loss,
        take_profit=take_profit,
        realized_pnl=pnl,
        reason=reason,
        price_source=price_source,
    )
    db.add(trade)
    db.commit()
    return trade


def summary(db: Session, starting_capital: float, marks: dict[str, float]) -> dict:
    trades = list_trades(db)
    led = replay(trades, starting_capital)
    positions: list[dict] = []
    market_value = 0.0
    for s, p in led.positions.items():
        mark = marks.get(s)
        value = p.quantity * (mark if mark is not None else p.avg_price)
        market_value += value
        positions.append(
            {
                "symbol": s,
                "quantity": p.quantity,
                "avg_price": round(p.avg_price, 4),
                "current_price": mark,
                "market_value": round(value, 2),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "unrealized_pnl": round((mark - p.avg_price) * p.quantity, 2) if mark is not None else None,
                "price_available": mark is not None,
            }
        )
    equity = led.cash + market_value
    for row in positions:
        row["exposure_pct"] = round(row["market_value"] / equity * 100, 2) if equity else 0
    return {
        "starting_capital": starting_capital,
        "cash": round(led.cash, 2),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
        "realized_pnl": round(led.realized_pnl, 2),
        "unrealized_pnl": round(sum(float(r["unrealized_pnl"] or 0) for r in positions), 2),
        "total_fees": round(led.fees, 2),
        "exposure_pct": round(market_value / equity * 100, 2) if equity else 0,
        "max_drawdown_pct": max_drawdown(equity_curve(trades, starting_capital, marks)),
        "positions": positions,
    }


def equity_curve(trades: list[PaperTrade], starting_capital: float, marks: dict[str, float]) -> list[float]:
    """Equity after each trade, marking holdings at the latest traded price; final point uses current marks."""
    led = Ledger(starting_capital, 0.0, 0.0, {})
    last_px: dict[str, float] = {}
    curve = [starting_capital]
    for t in trades:
        apply(led, t.symbol, t.side, t.quantity, t.price, t.fees, t.stop_loss, t.take_profit)
        last_px[t.symbol] = t.price
        curve.append(led.cash + sum(p.quantity * last_px[s] for s, p in led.positions.items()))
    if led.positions:
        curve.append(led.cash + sum(p.quantity * marks.get(s, last_px[s]) for s, p in led.positions.items()))
    return curve


def max_drawdown(curve: list[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak * 100)
    return round(mdd, 2)

"""Bar-by-bar backtest. Decision at bar t uses rows <= t (close of t); orders fill at the OPEN of t+1.
Stops/targets are checked intrabar against high/low; if both are touched in one bar the stop is assumed
first (conservative). Results are hypothetical and ignore liquidity, gaps beyond open, and taxes."""

from dataclasses import asdict, dataclass

import pandas as pd

from app.indicators.core import compute_all
from app.services.portfolio import position_size
from app.strategies.ema_crossover import STRATEGY_VERSION, Position, SignalType, StrategyConfig, evaluate_row


@dataclass
class BTTrade:
    entry_time: str
    entry_price: float
    exit_time: str | None
    exit_price: float | None
    quantity: int
    exit_reason: str | None
    pnl: float | None
    costs: float


def run_backtest(
    df: pd.DataFrame,
    cfg: StrategyConfig,
    initial_capital: float = 1_000_000,
    cost_bps: float = 10,
    slippage_bps: float = 5,
) -> dict:
    ind = compute_all(df)
    cash, qty = initial_capital, 0
    stop = target = None
    open_trade: BTTrade | None = None
    trades: list[BTTrade] = []
    pending: str | None = None
    pending_risk: dict = {}
    decisions: list[dict] = []
    curve: list[dict] = []
    cost_rate, slip = cost_bps / 10_000, slippage_bps / 10_000

    def close_position(i: int, raw_price: float, reason: str) -> None:
        nonlocal cash, qty, open_trade, stop, target
        px = raw_price * (1 - slip)
        fee = px * qty * cost_rate
        cash += px * qty - fee
        assert open_trade
        open_trade.exit_time, open_trade.exit_price, open_trade.exit_reason = str(ind.index[i]), round(px, 4), reason
        open_trade.costs += fee
        open_trade.pnl = round((px - open_trade.entry_price) * qty - open_trade.costs, 2)
        trades.append(open_trade)
        open_trade, qty, stop, target = None, 0, None, None

    for i in range(len(ind)):
        row = ind.iloc[i]
        # 1) fill yesterday's decision at today's open
        if pending == "BUY" and qty == 0:
            px = float(row["open"]) * (1 + slip)
            equity = cash
            size = position_size(
                equity,
                cash / (1 + cost_rate),
                px,
                pending_risk.get("stop_loss"),
                cfg.max_risk_per_trade_pct,
                cfg.max_portfolio_exposure_pct,
                0,
            )
            if size["quantity"] > 0:
                qty = size["quantity"]
                fee = px * qty * cost_rate
                cash -= px * qty + fee
                rps = pending_risk.get("risk_per_share")
                stop = px - rps if rps else None
                target = px + cfg.reward_risk_ratio * rps if rps else None
                open_trade = BTTrade(str(ind.index[i]), round(px, 4), None, None, qty, None, None, fee)
        elif pending == "SELL" and qty > 0:
            close_position(i, float(row["open"]), "signal: EMA cross down")
        pending = None

        # 2) intrabar stop / target on held position
        if qty > 0:
            if stop is not None and float(row["low"]) <= stop:
                close_position(i, min(stop, float(row["open"])), "stop-loss")
            elif target is not None and float(row["high"]) >= target:
                close_position(i, max(target, float(row["open"])), "take-profit")

        # 3) decide on this bar's close, for execution at the next open
        pos = Position(qty, open_trade.entry_price) if qty > 0 and open_trade else None
        res = evaluate_row(ind, i, cfg, pos)
        if res.signal_type != SignalType.HOLD:
            decisions.append({"time": str(ind.index[i]), "signal": res.signal_type.value, "close": res.price})
            pending, pending_risk = res.signal_type.value, res.risk
        curve.append({"time": str(ind.index[i]), "equity": round(cash + qty * float(row["close"]), 2)})

    open_position = None
    if open_trade:
        open_position = {**asdict(open_trade), "mark_price": float(ind["close"].iloc[-1])}
    final = curve[-1]["equity"] if curve else initial_capital
    peak, mdd = 0.0, 0.0
    for p in curve:
        peak = max(peak, p["equity"])
        mdd = max(mdd, (peak - p["equity"]) / peak * 100 if peak else 0)
    wins = [t for t in trades if (t.pnl or 0) > 0]
    first, last = (float(df["close"].iloc[0]), float(df["close"].iloc[-1])) if len(df) else (0, 0)
    return {
        "strategy_version": STRATEGY_VERSION,
        "bars": len(df),
        "start": str(df.index[0]) if len(df) else None,
        "end": str(df.index[-1]) if len(df) else None,
        "initial_capital": initial_capital,
        "final_equity": final,
        "total_return_pct": round((final / initial_capital - 1) * 100, 2),
        "buy_and_hold_return_pct": round((last / first - 1) * 100, 2) if first else None,
        "max_drawdown_pct": round(mdd, 2),
        "trades": [asdict(t) for t in trades],
        "num_trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "total_costs": round(sum(t.costs for t in trades), 2),
        "open_position": open_position,
        "decisions": decisions,
        "equity_curve": curve,
        "assumptions": {
            "signal_on": "completed daily bar close",
            "fill": "next bar open",
            "cost_bps_per_side": cost_bps,
            "slippage_bps_per_side": slippage_bps,
            "stop_vs_target_same_bar": "stop assumed first",
            "position_sizing": f"{cfg.max_risk_per_trade_pct}% equity risk, max exposure "
            f"{cfg.max_portfolio_exposure_pct}%",
            "disclaimer": "Hypothetical results. Past performance does not indicate future results.",
        },
    }

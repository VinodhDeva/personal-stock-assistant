"""Educational EMA-crossover strategy. These rules are examples, NOT a proven profitable strategy."""

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, Field

from app.indicators.core import compute_all

STRATEGY_ID = "ema_crossover"
STRATEGY_VERSION = "ema_crossover_v1"
MIN_BARS = 60  # SMA50 + headroom for EMA/MACD seeding and RSI


class SignalType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class StrategyConfig(BaseModel):
    rsi_buy_min: float = Field(45, ge=0, le=100, description="RSI must be at least this for a BUY")
    rsi_buy_max: float = Field(70, ge=0, le=100, description="RSI above this is treated as overbought")
    require_rsi_rising: bool = True
    require_close_above_sma20: bool = True
    volume_multiplier: float = Field(1.0, ge=0, description="Volume >= multiplier x 20-day average")
    atr_stop_multiplier: float = Field(2.0, gt=0, description="Stop-loss = entry - k x ATR(14)")
    reward_risk_ratio: float = Field(2.0, gt=0, description="Take-profit distance / stop distance")
    max_risk_per_trade_pct: float = Field(1.0, gt=0, le=10, description="% of equity risked per trade")
    max_portfolio_exposure_pct: float = Field(60, gt=0, le=100)


@dataclass
class Position:
    """Open paper position, used for exit rules."""

    quantity: float
    avg_price: float
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class SignalResult:
    signal_type: SignalType
    price: float | None
    bar_timestamp: datetime | None
    indicators: dict[str, float | None]
    rules_triggered: list[str]
    rules_failed: list[str]
    invalidation: list[str]
    risk: dict[str, float | None]
    strategy_version: str = STRATEGY_VERSION
    notes: list[str] = field(default_factory=list)


def _num(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 4)


def risk_levels(price: float, atr_value: float | None, cfg: StrategyConfig) -> dict[str, float | None]:
    if not atr_value:
        return {"stop_loss": None, "take_profit": None, "risk_per_share": None, "atr_14": atr_value}
    stop = price - cfg.atr_stop_multiplier * atr_value
    rps = price - stop
    return {
        "stop_loss": round(stop, 2),
        "take_profit": round(price + cfg.reward_risk_ratio * rps, 2),
        "risk_per_share": round(rps, 2),
        "atr_14": round(atr_value, 4),
    }


def evaluate_row(ind: pd.DataFrame, i: int, cfg: StrategyConfig, position: Position | None = None) -> SignalResult:
    """Decide using only rows <= i of an indicator frame (from compute_all). Used live and in backtests."""
    row, prev = ind.iloc[i], ind.iloc[i - 1] if i > 0 else None
    price = float(row["close"])
    keys = [
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
        "volume",
    ]
    indicators = {k: _num(row[k]) for k in keys}
    ts = ind.index[i].to_pydatetime()

    def hold(reason: str) -> SignalResult:
        return SignalResult(
            SignalType.HOLD, price, ts, indicators, [], [reason], [], risk_levels(price, indicators["atr_14"], cfg)
        )

    if i + 1 < MIN_BARS or prev is None:
        return hold(f"insufficient history: {i + 1} completed bars, need {MIN_BARS}")
    needed = ["rsi_14", "ema_12", "ema_26", "sma_20", "avg_volume_20", "atr_14"]
    if any(indicators[k] is None for k in needed) or any(_num(prev[k]) is None for k in ("ema_12", "ema_26", "rsi_14")):
        return hold("indicator values missing for the latest completed bar")

    e12, e26, pe12, pe26 = row["ema_12"], row["ema_26"], prev["ema_12"], prev["ema_26"]
    crossed_up = pe12 <= pe26 and e12 > e26
    crossed_down = pe12 >= pe26 and e12 < e26
    risk = risk_levels(price, indicators["atr_14"], cfg)

    # ---- exits (only meaningful with an open position, except the crossover) ----
    exit_rules: list[str] = []
    if position and position.quantity > 0:
        if position.stop_loss and float(row["low"]) <= position.stop_loss:
            exit_rules.append(f"stop-loss {position.stop_loss:.2f} reached (low {float(row['low']):.2f})")
        if position.take_profit and float(row["high"]) >= position.take_profit:
            exit_rules.append(f"take-profit {position.take_profit:.2f} reached (high {float(row['high']):.2f})")
    if crossed_down:
        exit_rules.append(f"EMA12 ({e12:.2f}) crossed below EMA26 ({e26:.2f}) on completed bar")
    if exit_rules:
        return SignalResult(
            SignalType.SELL, price, ts, indicators, exit_rules, [], ["EMA12 crosses back above EMA26"], risk
        )

    # ---- entry ----
    passed: list[str] = []
    failed: list[str] = []

    def check(ok: bool, met: str, not_met: str) -> None:
        if ok:
            passed.append(met)
        else:
            failed.append(not_met)

    emas = f"(EMA12 {e12:.2f}, EMA26 {e26:.2f})"
    check(
        bool(crossed_up),
        f"EMA12 crossed above EMA26 on completed bar {emas}",
        f"no fresh bullish EMA12/EMA26 crossover on the latest completed bar {emas}",
    )
    rsi_v, rsi_p = float(row["rsi_14"]), float(prev["rsi_14"])
    band = f"[{cfg.rsi_buy_min:g}, {cfg.rsi_buy_max:g}]"
    check(
        cfg.rsi_buy_min <= rsi_v <= cfg.rsi_buy_max, f"RSI {rsi_v:.1f} within {band}", f"RSI {rsi_v:.1f} outside {band}"
    )
    if cfg.require_rsi_rising:
        check(rsi_v > rsi_p, f"RSI rising ({rsi_p:.1f} -> {rsi_v:.1f})", f"RSI not rising ({rsi_p:.1f} -> {rsi_v:.1f})")
    if cfg.require_close_above_sma20:
        sma20 = float(row["sma_20"])
        check(
            price > sma20,
            f"close {price:.2f} above SMA20 {sma20:.2f}",
            f"close {price:.2f} not above SMA20 {sma20:.2f}",
        )
    vol, avg = float(row["volume"]), float(row["avg_volume_20"])
    need = f"{cfg.volume_multiplier:g} x avg {avg:,.0f}"
    check(vol >= cfg.volume_multiplier * avg, f"volume {vol:,.0f} >= {need}", f"volume {vol:,.0f} below {need}")

    if not failed and not (position and position.quantity > 0):
        invalidation = ["EMA12 crosses back below EMA26"]
        if risk["stop_loss"]:
            invalidation.append(f"close below stop-loss {risk['stop_loss']:.2f}")
        return SignalResult(SignalType.BUY, price, ts, indicators, passed, [], invalidation, risk)
    if not failed:
        failed.append("already holding a paper position")
    return SignalResult(SignalType.HOLD, price, ts, indicators, passed, failed, [], risk)


def completed_bars(df: pd.DataFrame, now: datetime, market_open_now: bool) -> pd.DataFrame:
    """Drops today's daily bar while the session is still running (it is not a completed candle)."""
    if df.empty or not market_open_now:
        return df
    last = df.index[-1].tz_convert(now.tzinfo) if df.index.tz is not None else df.index[-1]  # type: ignore[attr-defined]
    return df.iloc[:-1] if last.date() == now.date() else df


def evaluate(df: pd.DataFrame, cfg: StrategyConfig, position: Position | None = None) -> SignalResult:
    """Evaluate the last row of a *completed-bar* OHLCV frame."""
    if df.empty:
        return SignalResult(SignalType.HOLD, None, None, {}, [], ["no price data available"], [], {})
    return evaluate_row(compute_all(df), len(df) - 1, cfg, position)

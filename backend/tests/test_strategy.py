from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from app.strategies.ema_crossover import (
    MIN_BARS,
    Position,
    SignalType,
    StrategyConfig,
    completed_bars,
    evaluate,
)
from tests.conftest import buy_closes, full_cycle_closes, make_df

IST = ZoneInfo("Asia/Kolkata")


def test_buy_signal_with_rules_risk_and_invalidation():
    r = evaluate(make_df(buy_closes()), StrategyConfig())
    assert r.signal_type == SignalType.BUY
    assert any("crossed above" in t for t in r.rules_triggered)
    assert any("RSI" in t for t in r.rules_triggered)
    assert r.rules_failed == []
    assert r.risk["stop_loss"] < r.price < r.risk["take_profit"]
    assert any("crosses back below" in t for t in r.invalidation)
    assert r.strategy_version == "ema_crossover_v1"
    assert {"rsi_14", "ema_12", "ema_26", "atr_14", "macd"} <= r.indicators.keys()


def test_overbought_rsi_blocks_buy():
    r = evaluate(make_df(buy_closes()), StrategyConfig(rsi_buy_max=50))
    assert r.signal_type == SignalType.HOLD
    assert any("RSI" in f for f in r.rules_failed)


def test_volume_confirmation_blocks_buy():
    df = make_df(buy_closes())
    df.iloc[-1, df.columns.get_loc("volume")] = 100
    r = evaluate(df, StrategyConfig(volume_multiplier=1.0))
    assert r.signal_type == SignalType.HOLD
    assert any("volume" in f for f in r.rules_failed)


def test_no_buy_when_already_holding():
    r = evaluate(make_df(buy_closes()), StrategyConfig(), Position(10, 150))
    assert r.signal_type == SignalType.HOLD
    assert "already holding a paper position" in r.rules_failed


def test_sell_on_bearish_crossover():
    closes = full_cycle_closes()
    df = make_df(closes)
    sells = [i for i in range(MIN_BARS, len(df)) if evaluate(df.iloc[: i + 1], StrategyConfig()).signal_type == "SELL"]
    assert sells, "expected a bearish crossover in the decline"
    r = evaluate(df.iloc[: sells[0] + 1], StrategyConfig())
    assert any("crossed below" in t for t in r.rules_triggered)


def test_sell_on_stop_loss_and_take_profit():
    df = make_df(buy_closes())
    last = df["close"].iloc[-1]
    stop = evaluate(df, StrategyConfig(), Position(10, last, stop_loss=last * 1.5))
    assert stop.signal_type == SignalType.SELL and "stop-loss" in stop.rules_triggered[0]
    tp = evaluate(df, StrategyConfig(), Position(10, last, take_profit=last * 0.5))
    assert tp.signal_type == SignalType.SELL and "take-profit" in tp.rules_triggered[0]


def test_hold_with_insufficient_history():
    r = evaluate(make_df(buy_closes()[:40]), StrategyConfig())
    assert r.signal_type == SignalType.HOLD
    assert "insufficient history" in r.rules_failed[0]


def test_hold_on_empty_data():
    r = evaluate(make_df([1.0]).iloc[:0], StrategyConfig())
    assert r.signal_type == SignalType.HOLD and r.price is None


def test_hold_on_missing_indicator_values():
    df = make_df(buy_closes())
    df.iloc[-15:, df.columns.get_loc("high")] = np.nan  # ATR becomes NaN
    r = evaluate(df, StrategyConfig())
    assert r.signal_type == SignalType.HOLD
    assert "missing" in r.rules_failed[0]


def test_completed_bars_drops_todays_bar_only_while_open():
    df = make_df(buy_closes(), start="2026-06-01")
    today = df.index[-1].to_pydatetime().replace(hour=11, tzinfo=IST)
    assert len(completed_bars(df, today, market_open_now=True)) == len(df) - 1
    assert len(completed_bars(df, today, market_open_now=False)) == len(df)
    tomorrow = datetime(2030, 1, 1, 11, tzinfo=IST)
    assert len(completed_bars(df, tomorrow, market_open_now=True)) == len(df)


def test_thresholds_configurable():
    assert evaluate(make_df(buy_closes()), StrategyConfig(rsi_buy_min=69, rsi_buy_max=70)).signal_type == "HOLD"

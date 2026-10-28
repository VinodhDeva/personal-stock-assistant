import pandas as pd
import pytest

from app.backtesting.engine import run_backtest
from app.strategies.ema_crossover import StrategyConfig
from tests.conftest import full_cycle_closes, make_df


def bt(df, **kw):
    return run_backtest(df, StrategyConfig(), 1_000_000, **kw)


def test_fills_at_next_open_not_signal_close():
    df = make_df(full_cycle_closes())
    df["open"] = df["close"].shift(1).fillna(df["close"].iloc[0]) + 0.5  # opens distinct from prior close
    r = bt(df, cost_bps=0, slippage_bps=0)
    first_buy = next(d for d in r["decisions"] if d["signal"] == "BUY")
    entry = r["trades"][0] if r["trades"] else r["open_position"]
    i = list(map(str, df.index)).index(first_buy["time"])
    assert entry["entry_time"] == str(df.index[i + 1])
    assert entry["entry_price"] == pytest.approx(df["open"].iloc[i + 1], abs=1e-4)


def test_no_look_ahead_future_changes_do_not_alter_past_decisions():
    df = make_df(full_cycle_closes())
    k = 100
    base = bt(df.iloc[:k])
    altered = df.copy()
    altered.iloc[k:, :4] = altered.iloc[k:, :4] * 0.5  # crash the future
    full = bt(altered)
    past = [d for d in full["decisions"] if pd.Timestamp(d["time"]) < df.index[k - 1]]
    assert past == [d for d in base["decisions"] if pd.Timestamp(d["time"]) < df.index[k - 1]]
    assert full["equity_curve"][: k - 1] == base["equity_curve"][: k - 1]


def test_costs_and_slippage_reduce_returns():
    df = make_df(full_cycle_closes())
    free = bt(df, cost_bps=0, slippage_bps=0)
    costly = bt(df, cost_bps=50, slippage_bps=50)
    assert costly["final_equity"] < free["final_equity"]
    assert costly["total_costs"] > 0 == free["total_costs"]


def test_report_shape():
    r = bt(make_df(full_cycle_closes()))
    assert r["num_trades"] >= 1
    for k in ["total_return_pct", "buy_and_hold_return_pct", "max_drawdown_pct", "win_rate_pct", "assumptions"]:
        assert k in r
    assert r["assumptions"]["fill"] == "next bar open"


def test_stop_loss_intrabar():
    closes = full_cycle_closes()[:85]
    df = make_df(closes)
    r0 = bt(df, cost_bps=0, slippage_bps=0)
    assert r0["open_position"] or r0["trades"]
    entry_i = list(map(str, df.index)).index((r0["open_position"] or r0["trades"][0])["entry_time"])
    crash = df.copy()
    crash.iloc[entry_i + 1, crash.columns.get_loc("low")] = 1.0
    r = bt(crash, cost_bps=0, slippage_bps=0)
    assert r["trades"][0]["exit_reason"] == "stop-loss"
    assert r["trades"][0]["exit_time"] == str(df.index[entry_i + 1])

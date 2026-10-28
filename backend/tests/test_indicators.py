import math

import numpy as np
import pandas as pd
import pytest

from app.indicators.core import atr, compute_all, ema, macd, pct_change, rsi, sma
from tests.conftest import full_cycle_closes, make_df


def s(vals):
    return pd.Series(vals, dtype=float)


def test_sma():
    out = sma(s([1, 2, 3, 4, 5]), 3)
    assert out.isna().tolist()[:2] == [True, True]
    assert out.iloc[2:].tolist() == [2, 3, 4]


def test_ema_seeded_with_sma_and_recursive():
    vals = [1, 2, 3, 4, 5, 6]
    out = ema(s(vals), 3)
    assert math.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)  # SMA seed
    assert out.iloc[3] == pytest.approx(0.5 * 4 + 0.5 * 2.0)
    assert out.iloc[5] == pytest.approx(5.0)


def test_ema_short_series_all_nan():
    assert ema(s([1, 2]), 5).isna().all()


def test_rsi_extremes_and_range():
    assert rsi(s(range(1, 40)), 14).iloc[-1] == 100.0
    assert rsi(s(range(40, 1, -1)), 14).iloc[-1] == pytest.approx(0.0)
    assert rsi(s([10] * 30), 14).iloc[-1] == 50.0
    r = rsi(s(np.random.default_rng(1).normal(100, 2, 200)), 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_wilder_reference():
    # Classic Wilder example data (rounded closes). First RSI = 100 - 100 / (1 + avg_gain / avg_loss) with
    # gains summing to 3.34 and losses to 1.40 over 14 changes -> 70.46 (70.53 with the unrounded source data).
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    assert rsi(s(closes), 14).iloc[-1] == pytest.approx(100 - 100 / (1 + 3.34 / 1.40), abs=1e-6)


def test_macd_is_ema_difference():
    c = s(full_cycle_closes())
    m = macd(c)
    diff = (ema(c, 12) - ema(c, 26)).dropna()
    assert np.allclose(m["macd"].dropna(), diff)
    assert np.allclose((m["macd"] - m["macd_signal"]).dropna(), m["macd_hist"].dropna())
    assert m["macd_signal"].first_valid_index() == 25 + 8  # needs 26 bars for MACD, 9 more for its EMA


def test_atr_constant_range():
    df = pd.DataFrame({"open": [10.0] * 20, "high": [11.0] * 20, "low": [9.0] * 20, "close": [10.0] * 20})
    assert atr(df, 14).iloc[-1] == pytest.approx(2.0)
    assert atr(df, 14).iloc[:13].isna().all()


def test_atr_uses_gaps():
    df = pd.DataFrame({"open": [10, 20.0], "high": [11, 21.0], "low": [9, 19.0], "close": [10, 20.0]})
    tr_second = max(21 - 19, abs(21 - 10), abs(19 - 10))
    assert atr(df, 1).iloc[1] == pytest.approx(tr_second)


def test_pct_change():
    assert pct_change(s([100, 110, 99])).round(6).tolist()[1:] == [10.0, -10.0]


def test_compute_all_columns_and_avg_volume():
    out = compute_all(make_df(full_cycle_closes()))
    for col in [
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
    ]:
        assert col in out
    assert out["avg_volume_20"].iloc[-1] == 1_000_000


def test_indicators_are_causal():
    """Value at row t must not change when future rows are added or altered (no look-ahead)."""
    df = make_df(full_cycle_closes())
    full = compute_all(df)
    k = 90
    part = compute_all(df.iloc[:k])
    altered = df.copy()
    altered.iloc[k:, :4] *= 3
    alt = compute_all(altered)
    cols = ["rsi_14", "sma_20", "ema_26", "macd_signal", "atr_14"]
    pd.testing.assert_frame_equal(full[cols].iloc[:k], part[cols])
    pd.testing.assert_frame_equal(full[cols].iloc[:k], alt[cols].iloc[:k])

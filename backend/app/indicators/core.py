"""Technical indicators. Pure, causal functions: value at row t depends only on rows <= t."""

import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period, min_periods=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    # Seeded with the SMA of the first `period` values (standard convention), NaN before that.
    out = pd.Series(float("nan"), index=close.index)
    if len(close) < period:
        return out
    alpha = 2 / (period + 1)
    prev = close.iloc[:period].mean()
    out.iloc[period - 1] = prev
    for i in range(period, len(close)):
        prev = alpha * close.iloc[i] + (1 - alpha) * prev
        out.iloc[i] = prev
    return out


def _wilder(values: pd.Series, period: int) -> pd.Series:
    """Wilder smoothing seeded with the simple mean of the first `period` non-NaN values."""
    out = pd.Series(float("nan"), index=values.index)
    valid = values.dropna()
    if len(valid) < period:
        return out
    start = int(values.index.get_loc(valid.index[period - 1]))  # type: ignore[arg-type]
    prev = valid.iloc[:period].mean()
    out.iloc[start] = prev
    for i in range(start + 1, len(values)):
        prev = (prev * (period - 1) + values.iloc[i]) / period
        out.iloc[i] = prev
    return out


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    avg_gain = _wilder(delta.clip(lower=0), period)
    avg_loss = _wilder(-delta.clip(upper=0), period)
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # No losses in the window: RSI is 100 (or 50 when flat).
    out[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line.dropna(), signal).reindex(close.index)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1, skipna=False)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return _wilder(tr, period)


def pct_change(close: pd.Series, periods: int = 1) -> pd.Series:
    return close.pct_change(periods, fill_method=None) * 100


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the standard indicator columns to an OHLCV frame (columns: open, high, low, close, volume)."""
    out = df.copy()
    c = out["close"]
    out["rsi_14"] = rsi(c, 14)
    out["sma_20"] = sma(c, 20)
    out["sma_50"] = sma(c, 50)
    out["ema_12"] = ema(c, 12)
    out["ema_26"] = ema(c, 26)
    out = out.join(macd(c, 12, 26, 9))
    out["avg_volume_20"] = sma(out["volume"].astype(float), 20)
    out["atr_14"] = atr(out, 14)
    out["pct_change"] = pct_change(c)
    return out

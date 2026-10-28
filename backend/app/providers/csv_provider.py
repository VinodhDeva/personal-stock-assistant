import io
from pathlib import Path

import pandas as pd

from app.providers.base import (
    OHLCV,
    Bars,
    Capabilities,
    Freshness,
    MarketDataProvider,
    SymbolNotFound,
)

MAX_ROWS = 20_000


class CSVValidationError(ValueError):
    pass


def parse_ohlcv_csv(content: bytes, tz: str = "Asia/Kolkata") -> pd.DataFrame:
    """Strict parser for user uploads. Expected header: date,open,high,low,close,volume."""
    try:
        df = pd.read_csv(io.BytesIO(content), nrows=MAX_ROWS + 1)
    except Exception as e:
        raise CSVValidationError(f"not a readable CSV: {type(e).__name__}") from None
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in ["date", *OHLCV] if c not in df.columns]
    if missing:
        raise CSVValidationError(f"missing columns: {', '.join(missing)}")
    if df.empty:
        raise CSVValidationError("no rows")
    if len(df) > MAX_ROWS:
        raise CSVValidationError(f"too many rows (max {MAX_ROWS})")
    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.isna().any():
        raise CSVValidationError(f"invalid date on row {int(dates.isna().idxmax()) + 2}")  # type: ignore[call-overload]
    num = df[OHLCV].apply(pd.to_numeric, errors="coerce")
    bad = num.isna().any(axis=1) | (num[["open", "high", "low", "close"]] <= 0).any(axis=1) | (num["volume"] < 0)
    bad |= (num["high"] < num[["open", "close", "low"]].max(axis=1)) | (num["low"] > num[["open", "close"]].min(axis=1))
    if bad.any():
        raise CSVValidationError(f"invalid OHLCV values on row {int(bad.idxmax()) + 2}")
    idx = pd.DatetimeIndex(dates)
    num.index = idx.tz_localize(tz) if idx.tz is None else idx
    if num.index.duplicated().any():
        raise CSVValidationError("duplicate dates")
    return num.sort_index()


class CSVProvider(MarketDataProvider):
    """User-uploaded OHLCV files stored in data/uploads/<SYMBOL>.csv."""

    name = "csv"

    def __init__(self, uploads_dir: Path):
        self.dir = uploads_dir

    def is_configured(self) -> bool:
        return True

    def capabilities(self) -> Capabilities:
        return Capabilities(history=True, notes="Historical data from your uploads. Never live.")

    def path(self, symbol: str) -> Path:
        return self.dir / f"{symbol}.csv"

    def has(self, symbol: str) -> bool:
        return self.path(symbol).exists()

    def save(self, symbol: str, content: bytes) -> pd.DataFrame:
        df = parse_ohlcv_csv(content)
        self.dir.mkdir(parents=True, exist_ok=True)
        out = df.copy()
        out.index = out.index.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
        out.to_csv(self.path(symbol), index_label="date")
        return df

    def get_history(self, symbol: str, period: str = "max", interval: str = "1d") -> Bars:
        if not self.has(symbol):
            raise SymbolNotFound(f"no uploaded CSV for {symbol}")
        df = parse_ohlcv_csv(self.path(symbol).read_bytes())
        return Bars(symbol, df, self.name, "1d", Freshness.HISTORICAL)

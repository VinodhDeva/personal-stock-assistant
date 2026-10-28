import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import pandas as pd

SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}\.(NS|BO)$")
EXCHANGES = {"NS": "NSE", "BO": "BSE"}
OHLCV = ["open", "high", "low", "close", "volume"]


class Freshness(StrEnum):
    LIVE = "live"  # only when the provider confirms real-time
    DELAYED = "delayed"
    CACHED = "cached"
    HISTORICAL = "historical"
    STALE = "stale"


class ProviderError(Exception):
    """Base for provider failures. `retryable` drives backoff."""

    retryable = False


class ProviderThrottled(ProviderError):
    retryable = True


class ProviderUnavailable(ProviderError):
    retryable = True


class SymbolNotFound(ProviderError):
    pass


class NotSupported(ProviderError):
    pass


def normalize_symbol(raw: str, exchange: str | None = None) -> str:
    """'reliance' + NSE -> 'RELIANCE.NS'. Raises ValueError on anything else."""
    s = raw.strip().upper()
    if "." not in s:
        suffix = {"NSE": "NS", "BSE": "BO"}.get((exchange or "NSE").upper())
        if not suffix:
            raise ValueError("exchange must be NSE or BSE")
        s = f"{s}.{suffix}"
    if not SYMBOL_RE.match(s):
        raise ValueError("symbol must look like RELIANCE.NS (NSE) or RELIANCE.BO (BSE)")
    return s


def exchange_of(symbol: str) -> str:
    return EXCHANGES[symbol.rsplit(".", 1)[1]]


@dataclass
class Capabilities:
    quotes: bool = False
    history: bool = False
    intraday: bool = False
    realtime_confirmed: bool = False
    notes: str = ""


@dataclass
class Quote:
    symbol: str
    price: float
    previous_close: float | None
    data_timestamp: datetime
    provider: str
    freshness: Freshness
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    currency: str = "INR"

    @property
    def change_pct(self) -> float | None:
        if not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100


@dataclass
class Bars:
    symbol: str
    df: pd.DataFrame  # DatetimeIndex (tz-aware), columns OHLCV
    provider: str
    interval: str
    freshness: Freshness
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def data_timestamp(self) -> datetime | None:
        return None if self.df.empty else self.df.index[-1].to_pydatetime()


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    def get_quote(self, symbol: str) -> Quote:
        raise NotSupported(f"{self.name} does not provide quotes")

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> Bars:
        raise NotSupported(f"{self.name} does not provide history")


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns, drop rows without a close, sort, de-duplicate timestamps."""
    df = df.rename(columns=str.lower)
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ProviderError(f"missing columns: {missing}")
    df = df[OHLCV].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
    df["volume"] = df["volume"].fillna(0)
    return df[~df.index.duplicated(keep="last")].sort_index()

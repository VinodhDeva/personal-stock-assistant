from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from app.providers.base import (
    Bars,
    Capabilities,
    Freshness,
    MarketDataProvider,
    ProviderError,
    ProviderThrottled,
    ProviderUnavailable,
    Quote,
    SymbolNotFound,
    clean_ohlcv,
)
from app.providers.resilience import RateLimiter, TTLCache, with_retries

IST = ZoneInfo("Asia/Kolkata")


def to_av_symbol(symbol: str) -> str:
    # Alpha Vantage documents BSE as SYMBOL.BSE; NSE coverage on the free tier is not guaranteed.
    base, suffix = symbol.rsplit(".", 1)
    return f"{base}.{'BSE' if suffix == 'BO' else 'NSE'}"


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str | None, per_minute: int = 5, per_day: int = 25, client: httpx.Client | None = None):
        self.api_key = api_key
        self.limiter = RateLimiter({60: per_minute, 86400: per_day})
        self.cache = TTLCache()
        self.client = client or httpx.Client(timeout=20)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            quotes=True,
            history=True,
            intraday=False,
            realtime_confirmed=False,
            notes="Free tier: daily bars and end-of-day/delayed quotes, strict daily request quota.",
        )

    def _call(self, params: dict) -> dict:
        if not self.api_key:
            raise ProviderUnavailable("alpha vantage key not configured")
        # Throttling is checked before any network call so the quota is never exceeded.
        self.limiter.acquire()

        def call() -> dict:
            try:
                r = self.client.get(self.URL, params={**params, "apikey": self.api_key})
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise ProviderUnavailable(f"alpha vantage request failed: {type(e).__name__}") from None
            data = r.json()
            if "Note" in data or "Information" in data:
                raise ProviderThrottled("alpha vantage quota message received")
            if "Error Message" in data:
                raise SymbolNotFound(f"alpha vantage: unknown symbol {params.get('symbol')}")
            return data

        # One attempt only: a retry would spend scarce daily quota.
        return with_retries(call, attempts=1)

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> Bars:
        if interval != "1d":
            raise ProviderError("alpha vantage free tier: only daily interval supported here")
        key = ("hist", symbol)
        cached = self.cache.get(key, ttl=6 * 3600)
        if cached is not None:
            return Bars(symbol, cached.df, self.name, interval, Freshness.CACHED, cached.fetched_at)
        data = self._call({"function": "TIME_SERIES_DAILY", "symbol": to_av_symbol(symbol), "outputsize": "compact"})
        series = data.get("Time Series (Daily)") or {}
        if not series:
            raise SymbolNotFound(f"no data for {symbol}")
        df = pd.DataFrame.from_dict(series, orient="index").rename(columns=lambda c: c.split(". ", 1)[1])
        df.index = pd.DatetimeIndex(pd.to_datetime(df.index)).tz_localize(IST)
        bars = Bars(symbol, clean_ohlcv(df), self.name, "1d", Freshness.HISTORICAL)
        self.cache.set(key, bars)
        return bars

    def get_quote(self, symbol: str) -> Quote:
        key = ("quote", symbol)
        cached = self.cache.get(key, ttl=15 * 60)
        if cached is not None:
            return Quote(**{**cached.__dict__, "freshness": Freshness.CACHED})
        q = self._call({"function": "GLOBAL_QUOTE", "symbol": to_av_symbol(symbol)}).get("Global Quote") or {}
        if not q.get("05. price"):
            raise SymbolNotFound(f"no quote for {symbol}")
        day = datetime.fromisoformat(q["07. latest trading day"]).replace(tzinfo=IST)
        quote = Quote(
            symbol=symbol,
            price=float(q["05. price"]),
            previous_close=float(q["08. previous close"]) if q.get("08. previous close") else None,
            # Only the trading day is reported, not a time; keep the date and label it delayed.
            data_timestamp=day.astimezone(UTC),
            provider=self.name,
            freshness=Freshness.DELAYED,
        )
        self.cache.set(key, quote)
        return quote

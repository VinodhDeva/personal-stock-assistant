import logging
from datetime import UTC

import pandas as pd

from app.providers.base import (
    Bars,
    Capabilities,
    Freshness,
    MarketDataProvider,
    ProviderThrottled,
    ProviderUnavailable,
    Quote,
    SymbolNotFound,
    clean_ohlcv,
)
from app.providers.resilience import RateLimiter, TTLCache, with_retries

log = logging.getLogger(__name__)


class YahooProvider(MarketDataProvider):
    """Yahoo Finance via the unofficial yfinance library. Freshness is not guaranteed by Yahoo."""

    name = "yahoo"

    def __init__(self, enabled: bool = True, client: object | None = None):
        self.enabled = enabled
        self._client = client  # injectable for tests; defaults to the yfinance module
        # Self-imposed politeness limit; Yahoo publishes no official quota.
        self.limiter = RateLimiter({60: 60})
        self.cache = TTLCache()

    @property
    def yf(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import yfinance

            self._client = yfinance
        return self._client

    def is_configured(self) -> bool:
        return self.enabled

    def capabilities(self) -> Capabilities:
        return Capabilities(
            quotes=True,
            history=True,
            intraday=True,
            realtime_confirmed=False,
            notes="Unofficial. Quotes may be delayed; intraday history is limited and can be throttled.",
        )

    def _fetch(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        def call() -> pd.DataFrame:
            self.limiter.acquire()
            try:
                df = self.yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
            except Exception as e:  # yfinance raises many types, incl. YFRateLimitError
                text = f"{type(e).__name__}: {e}"
                if "RateLimit" in text or "Too Many Requests" in text:
                    raise ProviderThrottled(text) from e
                raise ProviderUnavailable(text) from e
            if df is None or df.empty:
                raise SymbolNotFound(f"no data for {symbol}")
            return df

        return with_retries(call)

    def get_history(self, symbol: str, period: str = "1y", interval: str = "1d") -> Bars:
        key = ("hist", symbol, period, interval)
        cached = self.cache.get(key, ttl=900 if interval == "1d" else 120)
        if cached is not None:
            return Bars(symbol, cached.df, self.name, interval, Freshness.CACHED, cached.fetched_at)
        df = self._fetch(symbol, period, interval)
        idx = pd.DatetimeIndex(df.index)
        df.index = idx.tz_localize("UTC") if idx.tz is None else idx
        df = clean_ohlcv(df)
        bars = Bars(symbol, df, self.name, interval, Freshness.DELAYED)
        self.cache.set(key, bars)
        return bars

    def get_quote(self, symbol: str) -> Quote:
        key = ("quote", symbol)
        cached = self.cache.get(key, ttl=60)
        if cached is not None:
            return Quote(**{**cached.__dict__, "freshness": Freshness.CACHED})
        # 1-minute bars give the timestamp of the last traded minute Yahoo has; fall back to daily.
        try:
            intraday = self._fetch(symbol, "1d", "1m")
            last_ts = pd.Timestamp(intraday.index[-1]).to_pydatetime()
            price = float(intraday["Close"].dropna().iloc[-1])
        except SymbolNotFound:
            intraday, last_ts, price = None, None, None
        daily = self._fetch(symbol, "5d", "1d")
        closes = daily["Close"].dropna()
        if price is None:
            price, last_ts = float(closes.iloc[-1]), pd.Timestamp(closes.index[-1]).to_pydatetime()
        assert last_ts is not None
        # previous close = the last daily close strictly before the quote's trading day
        prev = closes[[pd.Timestamp(i).date() < last_ts.date() for i in closes.index]]
        q = Quote(
            symbol=symbol,
            # yfinance returns float32 noise (1123.1500244); NSE/BSE tick size is 0.01 / 0.05.
            price=round(price, 2),
            previous_close=round(float(prev.iloc[-1]), 2) if len(prev) else None,
            data_timestamp=last_ts if last_ts.tzinfo else last_ts.replace(tzinfo=UTC),
            provider=self.name,
            freshness=Freshness.DELAYED,
        )
        self.cache.set(key, q)
        return q

    def search(self, query: str) -> list[dict]:
        try:
            res = self.yf.Search(query, max_results=10).quotes
        except Exception as e:
            log.warning("yahoo search failed: %s", e)
            return []
        return [
            {"symbol": r["symbol"], "name": r.get("shortname") or r.get("longname") or r["symbol"]}
            for r in res
            if str(r.get("symbol", "")).endswith((".NS", ".BO"))
        ]

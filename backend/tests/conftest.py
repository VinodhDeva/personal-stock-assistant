import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
        "SCHEDULER_ENABLED": "false",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "ALPHA_VANTAGE_API_KEY": "",
        "OLLAMA_BASE_URL": "http://127.0.0.1:9",  # nothing listens here: Ollama "unavailable"
        "UPLOADS_DIR": f"{_tmp}/uploads",
    }
)

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.providers.base import (  # noqa: E402
    Bars,
    Capabilities,
    Freshness,
    MarketDataProvider,
    ProviderUnavailable,
    Quote,
    SymbolNotFound,
)


def make_df(closes: list[float], start: str = "2025-01-01", volume: float = 1_000_000.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(closes), freq="B", tz="Asia/Kolkata")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": c.shift(1).fillna(c.iloc[0]), "high": c * 1.01, "low": c * 0.99, "close": c, "volume": volume}
    )


def buy_closes() -> list[float]:
    """Zigzag decline then zigzag rise: the last bar (index 79) is a confirmed EMA12/26 bullish crossover."""
    out, p = [], 200.0
    for i in range(70):
        p += -1.2 if i % 2 == 0 else 0.8
        out.append(round(p, 2))
    for i in range(10):
        p += 1.6 if i % 2 == 1 else -0.6
        out.append(round(p, 2))
    return out


def full_cycle_closes() -> list[float]:
    """Decline, rise (BUY at 79), extended rise, then decline (SELL crossover)."""
    out, p = [], 200.0
    for i in range(70):
        p += -1.2 if i % 2 == 0 else 0.8
        out.append(p)
    for i in range(40):
        p += 1.6 if i % 2 == 1 else -0.6
        out.append(p)
    out += [out[-1] - 2 * k for k in range(1, 20)]
    return out


class FakeProvider(MarketDataProvider):
    def __init__(
        self,
        name: str = "yahoo",
        data: dict[str, pd.DataFrame] | None = None,
        fail: Exception | None = None,
        quote_ts: datetime | None = None,
    ):
        self.name, self.data, self.fail, self.quote_ts = name, data or {}, fail, quote_ts
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def capabilities(self) -> Capabilities:
        return Capabilities(quotes=True, history=True, intraday=True)

    def _df(self, symbol: str) -> pd.DataFrame:
        self.calls += 1
        if self.fail:
            raise self.fail
        if symbol not in self.data:
            raise SymbolNotFound(symbol)
        return self.data[symbol]

    def get_history(self, symbol, period="1y", interval="1d"):  # type: ignore[no-untyped-def]
        return Bars(symbol, self._df(symbol), self.name, interval, Freshness.DELAYED)

    def get_quote(self, symbol):  # type: ignore[no-untyped-def]
        df = self._df(symbol)
        ts = self.quote_ts or df.index[-1].to_pydatetime()
        return Quote(symbol, float(df["close"].iloc[-1]), float(df["close"].iloc[-2]), ts, self.name, Freshness.DELAYED)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def fake_registry(monkeypatch):
    """Replaces the real providers with an in-memory one; no network in tests."""
    from app.providers.registry import get_registry

    reg = get_registry()
    fake = FakeProvider("yahoo", {"RELIANCE.NS": make_df(buy_closes()), "TCS.NS": make_df(full_cycle_closes())})
    from app.providers.csv_provider import CSVProvider

    monkeypatch.setattr(reg, "providers", {"yahoo": fake, "csv": CSVProvider(Path(_tmp) / "uploads")})
    # Treat data as fresh regardless of today's date.
    from app.services import market

    monkeypatch.setattr(market, "classify", lambda f, ts, now=None, daily=False: f)
    return fake


@pytest.fixture
def client(fake_registry):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def utc(*a: int) -> datetime:
    return datetime(*a, tzinfo=UTC)


__all__ = ["make_df", "buy_closes", "full_cycle_closes", "FakeProvider", "ProviderUnavailable", "utc"]

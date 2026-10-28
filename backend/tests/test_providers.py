import httpx
import pandas as pd
import pytest

from app.providers.alpha_vantage import AlphaVantageProvider, to_av_symbol
from app.providers.base import (
    Freshness,
    ProviderError,
    ProviderThrottled,
    ProviderUnavailable,
    SymbolNotFound,
    normalize_symbol,
)
from app.providers.csv_provider import CSVProvider, CSVValidationError, parse_ohlcv_csv
from app.providers.registry import ProviderRegistry
from app.providers.resilience import RateLimiter, TTLCache, with_retries
from app.providers.yahoo import YahooProvider
from tests.conftest import FakeProvider, buy_closes, make_df


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_normalize_symbol():
    assert normalize_symbol("reliance") == "RELIANCE.NS"
    assert normalize_symbol("tcs", "BSE") == "TCS.BO"
    assert normalize_symbol("M&M.NS") == "M&M.NS"
    for bad in ["AAPL.L", "X.XX", "", "DROP TABLE.NS", "A" * 30 + ".NS"]:
        with pytest.raises(ValueError):
            normalize_symbol(bad)
    with pytest.raises(ValueError):
        normalize_symbol("AAPL", "NASDAQ")


def test_rate_limiter_refuses_over_limit_and_recovers():
    clock = Clock()
    rl = RateLimiter({60: 2, 86400: 3}, clock)
    rl.acquire(), rl.acquire()
    with pytest.raises(ProviderThrottled):
        rl.acquire()
    clock.t = 61
    rl.acquire()
    clock.t = 130
    with pytest.raises(ProviderThrottled):  # daily cap of 3 reached
        rl.acquire()


def test_ttl_cache():
    clock = Clock()
    c = TTLCache(clock)
    c.set("k", 1)
    assert c.get("k", 10) == 1
    clock.t = 11
    assert c.get("k", 10) is None and c.get_any("k") == 1


def test_retries_with_exponential_backoff():
    sleeps, calls = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ProviderThrottled("429")
        return "ok"

    assert with_retries(flaky, attempts=3, base_delay=1, sleep=sleeps.append) == "ok"
    assert sleeps == [1, 2]


def test_retries_are_bounded_and_skip_non_retryable():
    sleeps = []
    with pytest.raises(ProviderUnavailable):
        with_retries(lambda: (_ for _ in ()).throw(ProviderUnavailable("down")), attempts=2, sleep=sleeps.append)
    assert len(sleeps) == 1
    with pytest.raises(SymbolNotFound):
        with_retries(lambda: (_ for _ in ()).throw(SymbolNotFound("x")), sleep=sleeps.append)
    assert len(sleeps) == 1


class FakeYF:
    def __init__(self, exc=None, df=None):
        self.exc, self.df = exc, df

    def Ticker(self, symbol):  # noqa: N802
        outer = self

        class T:
            def history(self, **kw):
                if outer.exc:
                    raise outer.exc
                return outer.df

        return T()


def test_yahoo_maps_rate_limit_to_throttled(monkeypatch):
    monkeypatch.setattr("app.providers.resilience.time.sleep", lambda s: None)

    class YFRateLimitError(Exception):
        pass

    y = YahooProvider(client=FakeYF(exc=YFRateLimitError("Too Many Requests. Rate limited.")))
    with pytest.raises(ProviderThrottled):
        y.get_history("RELIANCE.NS")


def test_yahoo_empty_frame_is_symbol_not_found():
    y = YahooProvider(client=FakeYF(df=pd.DataFrame()))
    with pytest.raises(SymbolNotFound):
        y.get_history("NOPE.NS")


def test_yahoo_history_labelled_delayed_then_cached():
    df = make_df(buy_closes()).rename(columns=str.title)
    df.index = df.index.tz_localize(None)
    y = YahooProvider(client=FakeYF(df=df))
    first = y.get_history("RELIANCE.NS")
    assert first.freshness == Freshness.DELAYED and first.df.index.tz is not None
    assert y.get_history("RELIANCE.NS").freshness == Freshness.CACHED
    assert y.capabilities().realtime_confirmed is False


def _av(handler, per_minute=5, per_day=25):
    return AlphaVantageProvider(
        "demo-key", per_minute, per_day, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_alpha_vantage_quota_message_is_throttle():
    av = _av(lambda req: httpx.Response(200, json={"Note": "Thank you for using Alpha Vantage! ... limit"}))
    with pytest.raises(ProviderThrottled):
        av.get_quote("RELIANCE.BO")


def test_alpha_vantage_never_exceeds_local_limit():
    hits = []

    def handler(req):
        hits.append(req)
        return httpx.Response(
            200,
            json={
                "Global Quote": {"05. price": "100", "08. previous close": "99", "07. latest trading day": "2026-10-27"}
            },
        )

    av = _av(handler, per_minute=2, per_day=2)
    av.get_quote("A.BO")
    av.get_quote("B.BO")
    with pytest.raises(ProviderThrottled):
        av.get_quote("C.BO")
    assert len(hits) == 2
    assert av.get_quote("A.BO").freshness == Freshness.CACHED  # cache hit costs no quota
    assert len(hits) == 2


def test_alpha_vantage_errors_do_not_leak_key():
    av = _av(lambda req: (_ for _ in ()).throw(httpx.ConnectError("boom", request=req)))
    with pytest.raises(ProviderUnavailable) as e:
        av.get_quote("A.BO")
    assert "demo-key" not in str(e.value)
    assert to_av_symbol("RELIANCE.BO") == "RELIANCE.BSE"


def test_registry_falls_back_and_reports_it():
    bad = FakeProvider("yahoo", fail=ProviderThrottled("429"))
    good = FakeProvider("alpha_vantage", {"X.NS": make_df(buy_closes())})
    reg = ProviderRegistry([bad, good])
    quote, notes = reg.get_quote("X.NS")
    assert quote.provider == "alpha_vantage"
    assert notes and "yahoo" in notes[0]
    assert reg.status()[0]["last_error"]


def test_registry_symbol_not_found_vs_unavailable():
    reg = ProviderRegistry([FakeProvider("yahoo", {})])
    with pytest.raises(SymbolNotFound):
        reg.get_quote("NOPE.NS")
    reg = ProviderRegistry([FakeProvider("yahoo", fail=ProviderUnavailable("down"))])
    with pytest.raises(ProviderError):
        reg.get_quote("X.NS")


GOOD_CSV = b"date,open,high,low,close,volume\n2026-01-01,10,11,9,10.5,100\n2026-01-02,10.5,12,10,11,200\n"


def test_csv_parse_valid(tmp_path):
    df = parse_ohlcv_csv(GOOD_CSV)
    assert len(df) == 2 and df.index.tz is not None
    p = CSVProvider(tmp_path)
    p.save("X.NS", GOOD_CSV)
    bars = p.get_history("X.NS")
    assert bars.freshness == Freshness.HISTORICAL and len(bars.df) == 2


@pytest.mark.parametrize(
    "content,msg",
    [
        (b"date,open,high\n2026-01-01,1,2\n", "missing columns"),
        (b"date,open,high,low,close,volume\n", "no rows"),
        (b"date,open,high,low,close,volume\nnotadate,1,2,1,1,1\n", "invalid date"),
        (b"date,open,high,low,close,volume\n2026-01-01,10,9,8,10,1\n", "invalid OHLCV"),
        (b"date,open,high,low,close,volume\n2026-01-01,-1,9,8,10,1\n", "invalid OHLCV"),
        (b"date,open,high,low,close,volume\n2026-01-01,10,11,9,10,1\n2026-01-01,10,11,9,10,1\n", "duplicate"),
        (b"\x00\x01\x02", "missing columns|not a readable"),
    ],
)
def test_csv_rejects_malformed(content, msg):
    with pytest.raises(CSVValidationError, match=msg):
        parse_ohlcv_csv(content)

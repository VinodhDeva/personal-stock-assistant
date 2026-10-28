import httpx
import pytest
from sqlalchemy import select

from app.models import NotificationLog, Signal
from app.notifications.notifier import Notifier, format_signal
from app.notifications.telegram import TelegramClient, TelegramError
from app.providers.base import Freshness, ProviderUnavailable
from app.providers.registry import ProviderRegistry
from app.services import market
from app.services.signals import evaluate_symbol
from app.strategies.ema_crossover import StrategyConfig
from tests.conftest import FakeProvider, buy_closes, make_df


@pytest.fixture
def reg(monkeypatch):
    monkeypatch.setattr(market, "classify", lambda f, ts, now=None, daily=False: f)
    return ProviderRegistry([FakeProvider("yahoo", {"RELIANCE.NS": make_df(buy_closes())})])


def test_signal_persisted_with_full_metadata(db, reg):
    ev = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000)
    s = ev.signal
    assert ev.is_new and s.signal_type == "BUY"
    assert s.exchange == "NSE" and s.provider == "yahoo" and s.freshness == "delayed"
    assert s.data_timestamp and s.price and s.rules_triggered and s.invalidation and s.risk["stop_loss"]
    assert s.strategy_version == "ema_crossover_v1"


def test_same_bar_is_deduplicated(db, reg):
    a = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000)
    b = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000)
    assert a.is_new and not b.is_new and a.signal.id == b.signal.id
    assert len(db.scalars(select(Signal)).all()) == 1


def test_stale_data_downgrades_to_hold(db, monkeypatch):
    monkeypatch.setattr(market, "classify", lambda f, ts, now=None, daily=False: Freshness.STALE)
    reg = ProviderRegistry([FakeProvider("yahoo", {"RELIANCE.NS": make_df(buy_closes())})])
    s = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000).signal
    assert s.signal_type == "HOLD" and "stale" in s.rules_failed[0]


def test_provider_failure_gives_hold(db):
    reg = ProviderRegistry([FakeProvider("yahoo", fail=ProviderUnavailable("down"))])
    s = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000).signal
    assert s.signal_type == "HOLD" and "unavailable" in s.rules_failed[0]


def test_notifier_local_log_and_cooldown(db):
    n = Notifier(None, cooldown_minutes=60)
    assert n.notify(db, "k1", "signal", "hello").status == "logged"
    assert n.notify(db, "k1", "signal", "hello").status == "suppressed"
    assert n.notify(db, "k2", "signal", "other").status == "logged"
    assert len(db.scalars(select(NotificationLog)).all()) == 3


class FakeTelegram:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, text):
        if self.fail:
            raise TelegramError("telegram send failed: HTTP 401")
        self.sent.append(text)


def test_notifier_telegram_sent_and_failure_logged(db):
    tg = FakeTelegram()
    assert Notifier(tg, 60).notify(db, "a", "signal", "x").status == "sent"  # type: ignore[arg-type]
    failed = Notifier(FakeTelegram(fail=True), 60).notify(db, "b", "signal", "x")  # type: ignore[arg-type]
    assert failed.status == "failed" and "401" in failed.error
    # a failed attempt does not start the cooldown
    assert Notifier(tg, 60).notify(db, "b", "signal", "x").status == "sent"  # type: ignore[arg-type]


def test_telegram_retries_then_succeeds_without_leaking_token():
    calls, sleeps = [], []

    def handler(req):
        calls.append(req)
        return httpx.Response(500 if len(calls) < 3 else 200, json={})

    tg = TelegramClient(
        "123:SECRET", "42", client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append
    )
    tg.send("hi")
    assert len(calls) == 3 and sleeps == [1, 2]

    def down(req):
        raise httpx.ConnectError("no route", request=req)

    tg = TelegramClient(
        "123:SECRET", "42", client=httpx.Client(transport=httpx.MockTransport(down)), sleep=lambda s: None
    )
    with pytest.raises(TelegramError) as e:
        tg.send("hi")
    assert "SECRET" not in str(e.value)


def test_telegram_does_not_retry_auth_errors():
    calls = []
    tg = TelegramClient(
        "t",
        "c",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(401, json={}))),
        sleep=lambda s: None,
    )
    with pytest.raises(TelegramError):
        tg.send("x")
    assert len(calls) == 1


def test_signal_message_contents(db, reg):
    s = evaluate_symbol(db, reg, "RELIANCE.NS", StrategyConfig(), 1_000_000).signal
    text = format_signal(s, "http://localhost:5173")
    for part in [
        "RELIANCE.NS (NSE)",
        "Price at evaluation",
        "Data timestamp",
        "stop",
        "not advice",
        "http://localhost:5173/stocks/RELIANCE.NS",
    ]:
        assert part in text

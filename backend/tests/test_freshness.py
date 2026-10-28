from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.market_hours import is_market_open, is_trading_day
from app.providers.base import Freshness
from app.services.market import classify, last_session_date

IST = ZoneInfo("Asia/Kolkata")
WED_NOON = datetime(2026, 10, 28, 12, 0, tzinfo=IST)  # Wednesday


def test_market_hours_weekend_and_holiday():
    assert is_market_open(WED_NOON)
    assert not is_market_open(WED_NOON.replace(hour=8))
    assert not is_market_open(datetime(2026, 10, 31, 12, tzinfo=IST))  # Saturday
    assert not is_trading_day(datetime(2026, 10, 2).date())  # Gandhi Jayanti (holiday file)


def test_last_session_date_skips_weekend():
    monday_early = datetime(2026, 11, 2, 8, tzinfo=IST)
    assert last_session_date(monday_early).isoformat() == "2026-10-30"


def test_quote_stale_during_market_hours():
    assert classify(Freshness.DELAYED, WED_NOON - timedelta(minutes=5), WED_NOON) == Freshness.DELAYED
    assert classify(Freshness.DELAYED, WED_NOON - timedelta(hours=2), WED_NOON) == Freshness.STALE


def test_quote_after_close_uses_session_date():
    evening = WED_NOON.replace(hour=20)
    assert classify(Freshness.DELAYED, WED_NOON.replace(hour=15, minute=29), evening) == Freshness.DELAYED
    assert classify(Freshness.DELAYED, WED_NOON - timedelta(days=1), evening) == Freshness.STALE


def test_daily_bars_need_last_completed_session():
    yesterday_bar = datetime(2026, 10, 27, 0, 0, tzinfo=IST)
    assert classify(Freshness.DELAYED, yesterday_bar, WED_NOON, daily=True) == Freshness.DELAYED
    assert classify(Freshness.DELAYED, yesterday_bar - timedelta(days=3), WED_NOON, daily=True) == Freshness.STALE


def test_missing_timestamp_is_stale_and_historical_stays_historical():
    assert classify(Freshness.DELAYED, None, WED_NOON) == Freshness.STALE
    assert classify(Freshness.HISTORICAL, WED_NOON - timedelta(days=400), WED_NOON) == Freshness.HISTORICAL


def test_never_live_without_provider_confirmation():
    assert classify(Freshness.DELAYED, WED_NOON, WED_NOON) != Freshness.LIVE

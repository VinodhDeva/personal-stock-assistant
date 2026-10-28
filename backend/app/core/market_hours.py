import json
import logging
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings

log = logging.getLogger(__name__)


def market_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().market_timezone)


def now_market() -> datetime:
    return datetime.now(market_tz())


@lru_cache
def holidays() -> frozenset[date]:
    path = get_settings().holidays_file
    try:
        raw = json.loads(path.read_text())
        return frozenset(date.fromisoformat(d["date"]) for d in raw.get("holidays", []))
    except FileNotFoundError:
        log.warning("Holiday file %s missing; only weekends are treated as closed", path)
        return frozenset()


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays()


def is_market_open(at: datetime | None = None) -> bool:
    s = get_settings()
    at = (at or now_market()).astimezone(market_tz())
    return is_trading_day(at.date()) and s.market_open <= at.time() <= s.market_close

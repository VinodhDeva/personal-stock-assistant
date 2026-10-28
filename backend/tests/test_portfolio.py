import pytest

from app.core.errors import AppError
from app.services.portfolio import (
    equity_curve,
    list_trades,
    max_drawdown,
    position_size,
    record_trade,
    summary,
)

CAP = 100_000


def trade(db, side, qty, price, **kw):
    return record_trade(
        db, starting_capital=CAP, symbol=kw.pop("symbol", "INFY.NS"), side=side, quantity=qty, price=price, **kw
    )


def test_average_cost_and_realized_pnl(db):
    trade(db, "BUY", 10, 100, fees=10)
    trade(db, "BUY", 10, 120)
    t = trade(db, "SELL", 5, 130, fees=5)
    assert t.realized_pnl == pytest.approx((130 - 110) * 5 - 5)
    s = summary(db, CAP, {"INFY.NS": 140})
    pos = s["positions"][0]
    assert pos["quantity"] == 15 and pos["avg_price"] == 110
    assert pos["unrealized_pnl"] == pytest.approx(15 * 30)
    assert s["cash"] == pytest.approx(CAP - 1000 - 10 - 1200 + 650 - 5)
    assert s["equity"] == pytest.approx(s["cash"] + 15 * 140)
    assert s["total_fees"] == 15


def test_position_closed_fully(db):
    trade(db, "BUY", 10, 100)
    trade(db, "SELL", 10, 90)
    s = summary(db, CAP, {})
    assert s["positions"] == [] and s["realized_pnl"] == -100 and s["equity"] == CAP - 100


def test_rejects_short_and_overspend(db):
    with pytest.raises(AppError, match="short selling"):
        trade(db, "SELL", 1, 100)
    with pytest.raises(AppError) as e:
        trade(db, "BUY", 10_000, 100)
    assert e.value.code == "insufficient_cash"
    assert list_trades(db) == []


def test_risk_and_exposure_limits(db):
    with pytest.raises(AppError) as e:
        trade(db, "BUY", 100, 100, stop_loss=80, risk_pct=1)  # risks 2,000 > 1% of 100k
    assert e.value.code == "risk_limit"
    with pytest.raises(AppError) as e:
        trade(db, "BUY", 700, 100, max_exposure_pct=60)
    assert e.value.code == "exposure_limit"
    with pytest.raises(AppError):
        trade(db, "BUY", 1, 100, stop_loss=101)
    trade(db, "BUY", 50, 100, stop_loss=80, risk_pct=1, max_exposure_pct=60)


def test_position_size():
    r = position_size(
        equity=100_000, cash=100_000, entry=100, stop=95, risk_pct=1, max_exposure_pct=60, current_exposure=0
    )
    assert r["quantity"] == 200 and r["risk_amount"] == 1000
    capped = position_size(100_000, 100_000, 100, 99.9, 1, 10, 0)
    assert capped["quantity"] == 100  # exposure cap: 10% of 100k / 100
    assert position_size(100_000, 500, 100, None, 1, 100, 0)["quantity"] == 5  # cash cap


def test_drawdown(db):
    assert max_drawdown([100, 120, 90, 130]) == 25.0
    trade(db, "BUY", 100, 100)
    trade(db, "SELL", 100, 80)
    curve = equity_curve(list_trades(db), CAP, {})
    assert curve[-1] == CAP - 2000
    assert summary(db, CAP, {})["max_drawdown_pct"] == 2.0


def test_missing_price_reported_not_invented(db):
    trade(db, "BUY", 1, 100)
    pos = summary(db, CAP, {})["positions"][0]
    assert pos["current_price"] is None and pos["unrealized_pnl"] is None and not pos["price_available"]

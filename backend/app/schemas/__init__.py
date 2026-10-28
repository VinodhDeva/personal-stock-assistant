from typing import Literal

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=24, examples=["RELIANCE.NS", "TCS"])
    exchange: Literal["NSE", "BSE"] | None = None
    name: str | None = Field(None, max_length=128)
    notify_signals: bool = True
    validate_symbol: bool = Field(True, description="Check with a data provider that the symbol has data")


class WatchlistUpdate(BaseModel):
    notify_signals: bool


class AlertCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    condition: Literal["above", "below"]
    price: float = Field(gt=0, lt=10_000_000)
    note: str | None = Field(None, max_length=200)


class PaperTradeCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0, le=1_000_000)
    price: float | None = Field(None, gt=0, description="Defaults to the latest available quote")
    fees: float = Field(0, ge=0, le=1_000_000)
    stop_loss: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    reason: str | None = Field(None, max_length=200)
    enforce_risk_limits: bool = True


class PositionSizeRequest(BaseModel):
    entry: float = Field(gt=0)
    stop_loss: float | None = Field(None, gt=0)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    symbol: str | None = Field(None, max_length=24)


class SchedulerSettings(BaseModel):
    refresh_interval_seconds: int = Field(ge=60, le=86_400)

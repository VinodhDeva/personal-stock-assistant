import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import NotificationLog
from app.notifications.telegram import TelegramClient, TelegramError

log = logging.getLogger(__name__)


class Notifier:
    """Sends via Telegram when configured, otherwise logs locally. Dedupes by key within a cooldown."""

    def __init__(self, telegram: TelegramClient | None, cooldown_minutes: int):
        self.telegram = telegram
        self.cooldown = timedelta(minutes=cooldown_minutes)

    @property
    def channel(self) -> str:
        return "telegram" if self.telegram else "local"

    def notify(self, db: Session, key: str, kind: str, text: str) -> NotificationLog:
        since = datetime.now(UTC) - self.cooldown
        recent = db.scalars(
            select(NotificationLog).where(
                NotificationLog.key == key,
                NotificationLog.status.in_(["sent", "logged"]),
                NotificationLog.created_at >= since,
            )
        ).first()
        if recent:
            entry = NotificationLog(key=key, kind=kind, channel=self.channel, status="suppressed", message=text)
        elif self.telegram:
            try:
                self.telegram.send(text)
                entry = NotificationLog(key=key, kind=kind, channel="telegram", status="sent", message=text)
            except TelegramError as e:
                log.error("telegram notification failed: %s", e)
                entry = NotificationLog(
                    key=key, kind=kind, channel="telegram", status="failed", message=text, error=str(e)[:300]
                )
        else:
            log.info("[notification:%s] %s", kind, text.replace("\n", " | "))
            entry = NotificationLog(key=key, kind=kind, channel="local", status="logged", message=text)
        db.add(entry)
        db.commit()
        return entry


def get_notifier() -> Notifier:
    s = get_settings()
    tg = (
        TelegramClient(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id)
        if s.telegram_bot_token and s.telegram_chat_id
        else None
    )
    return Notifier(tg, s.notification_cooldown_minutes)


def format_signal(sig, dashboard_url: str) -> str:  # type: ignore[no-untyped-def]
    risk = sig.risk or {}
    lines = [
        f"Potential {sig.signal_type} setup: {sig.symbol} ({sig.exchange})",
        f"Price at evaluation: INR {sig.price:,.2f}" if sig.price is not None else "Price: unavailable",
        f"Data timestamp: {sig.data_timestamp:%Y-%m-%d %H:%M %Z} ({sig.freshness}, via {sig.provider})"
        if sig.data_timestamp
        else "Data timestamp: unknown",
        "Why:",
        *[f"- {r}" for r in sig.rules_triggered],
    ]
    if risk.get("stop_loss"):
        lines.append(f"Risk: stop {risk['stop_loss']:,.2f} | target {risk['take_profit']:,.2f} | ATR {risk['atr_14']}")
    if sig.invalidation:
        lines.append("Invalidated if: " + "; ".join(sig.invalidation))
    lines += [
        f"Strategy: {sig.strategy_version}. Educational signal, not advice. Paper trading only.",
        f"{dashboard_url}/stocks/{sig.symbol}",
    ]
    return "\n".join(lines)

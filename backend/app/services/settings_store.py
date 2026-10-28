from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppSetting
from app.strategies.ema_crossover import StrategyConfig


def get_strategy_config(db: Session) -> StrategyConfig:
    row = db.get(AppSetting, "strategy")
    return StrategyConfig(**(row.value if row else {}))


def set_strategy_config(db: Session, cfg: StrategyConfig) -> StrategyConfig:
    row = db.get(AppSetting, "strategy") or AppSetting(key="strategy", value={})
    row.value = cfg.model_dump()
    db.add(row)
    db.commit()
    return cfg


def get_refresh_interval(db: Session) -> int:
    row = db.get(AppSetting, "scheduler")
    return int((row.value if row else {}).get("refresh_interval_seconds", get_settings().refresh_interval_seconds))


def set_refresh_interval(db: Session, seconds: int) -> None:
    row = db.get(AppSetting, "scheduler") or AppSetting(key="scheduler", value={})
    row.value = {"refresh_interval_seconds": seconds}
    db.add(row)
    db.commit()

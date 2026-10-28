import logging
from dataclasses import asdict
from functools import lru_cache

from app.core.config import get_settings
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import Bars, MarketDataProvider, NotSupported, ProviderError, Quote, SymbolNotFound
from app.providers.broker import BrokerDataProvider
from app.providers.csv_provider import CSVProvider
from app.providers.yahoo import YahooProvider

log = logging.getLogger(__name__)


class ProviderRegistry:
    """Picks a provider per operation and records which one answered (never a silent swap)."""

    def __init__(self, providers: list[MarketDataProvider]):
        self.providers = {p.name: p for p in providers}
        self.last_errors: dict[str, str] = {}

    def configured(self, op: str) -> list[MarketDataProvider]:
        return [p for p in self.providers.values() if p.is_configured() and getattr(p.capabilities(), op)]

    def status(self) -> list[dict]:
        return [
            {
                "name": p.name,
                "configured": p.is_configured(),
                "capabilities": asdict(p.capabilities()),
                "last_error": self.last_errors.get(p.name),
            }
            for p in self.providers.values()
        ]

    def _try(self, op: str, order: list[MarketDataProvider], call):  # type: ignore[no-untyped-def]
        errors: list[str] = []
        not_found = 0
        for p in order:
            try:
                result = call(p)
                self.last_errors.pop(p.name, None)
                return result, errors
            except NotSupported:
                continue
            except SymbolNotFound as e:
                not_found += 1
                errors.append(f"{p.name}: {e}")
            except ProviderError as e:
                self.last_errors[p.name] = str(e)
                errors.append(f"{p.name}: {e}")
                log.warning("%s %s failed: %s", p.name, op, e)
        if order and not_found == len(errors) and errors:
            raise SymbolNotFound("; ".join(errors))
        raise ProviderError("; ".join(errors) or f"no provider configured for {op}")

    def get_quote(self, symbol: str, provider: str | None = None) -> tuple[Quote, list[str]]:
        order = [self.providers[provider]] if provider else self.configured("quotes")
        return self._try("quote", order, lambda p: p.get_quote(symbol))

    def get_history(
        self, symbol: str, period: str = "1y", interval: str = "1d", provider: str | None = None
    ) -> tuple[Bars, list[str]]:
        if provider:
            order = [self.providers[provider]]
        else:
            order = self.configured("history")
            csv = self.providers.get("csv")
            # Uploaded data is only used when explicitly requested, or when nothing else answers.
            order = [p for p in order if p.name != "csv"] + ([csv] if csv else [])
            if interval != "1d":
                order = [p for p in order if p.capabilities().intraday]
        return self._try("history", order, lambda p: p.get_history(symbol, period, interval))


@lru_cache
def get_registry() -> ProviderRegistry:
    s = get_settings()
    key = s.alpha_vantage_api_key.get_secret_value() if s.alpha_vantage_api_key else None
    return ProviderRegistry(
        [
            YahooProvider(enabled=s.yahoo_enabled),
            AlphaVantageProvider(key, s.alpha_vantage_per_minute_limit, s.alpha_vantage_daily_limit),
            CSVProvider(s.uploads_dir),
            BrokerDataProvider(),
        ]
    )

"""Extension point for a future, *authorized* Indian broker data feed (e.g. a broker's official API).

Deliberately not implemented. A real implementation must use the broker's documented auth flow,
respect its rate limits and exchange data-redistribution terms, and must stay read-only:
this application never places orders.
"""

from app.providers.base import Capabilities, MarketDataProvider


class BrokerDataProvider(MarketDataProvider):
    name = "broker"

    def is_configured(self) -> bool:
        return False

    def capabilities(self) -> Capabilities:
        return Capabilities(notes="Not implemented. Reserved for an authorized broker market-data feed.")

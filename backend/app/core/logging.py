import logging

from app.core.config import get_settings


class RedactSecretsFilter(logging.Filter):
    """Masks configured secrets in every log record, wherever they appear."""

    def __init__(self) -> None:
        super().__init__()
        s = get_settings()
        self.secrets = [v.get_secret_value() for v in (s.alpha_vantage_api_key, s.telegram_bot_token) if v]

    def filter(self, record: logging.LogRecord) -> bool:
        if self.secrets:
            msg = record.getMessage()
            for secret in self.secrets:
                msg = msg.replace(secret, "***")
            record.msg, record.args = msg, None
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactSecretsFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # httpx logs full request URLs, and the Telegram token is part of the URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)

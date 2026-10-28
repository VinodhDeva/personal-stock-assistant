import time
from collections.abc import Callable

import httpx


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(
        self, token: str, chat_id: str, client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ):
        self.token, self.chat_id = token, chat_id
        self.client = client or httpx.Client(timeout=15)
        self.sleep = sleep

    def send(self, text: str, attempts: int = 3) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        last = ""
        for attempt in range(attempts):
            try:
                r = self.client.post(
                    url, json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
                )
                if r.status_code == 200:
                    return
                last = f"HTTP {r.status_code}"
                if r.status_code == 429:
                    retry_after = float(r.json().get("parameters", {}).get("retry_after", 2**attempt))
                    self.sleep(min(retry_after, 30))
                    continue
                if 400 <= r.status_code < 500:
                    break  # bad token / chat id: retrying will not help
            except httpx.HTTPError as e:
                # Never include the URL: it contains the bot token.
                last = type(e).__name__
            self.sleep(2**attempt)
        raise TelegramError(f"telegram send failed: {last}")

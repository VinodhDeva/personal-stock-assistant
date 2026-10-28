import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any, TypeVar

from app.providers.base import ProviderError, ProviderThrottled

log = logging.getLogger(__name__)
T = TypeVar("T")


class RateLimiter:
    """Sliding-window limits, e.g. {60: 5, 86400: 25}. `acquire` refuses instead of waiting."""

    def __init__(self, limits: dict[int, int], clock: Callable[[], float] = time.monotonic):
        self.limits, self.clock = limits, clock
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = self.clock()
            longest = max(self.limits)
            while self.calls and now - self.calls[0] >= longest:
                self.calls.popleft()
            for window, limit in self.limits.items():
                if sum(1 for t in self.calls if now - t < window) >= limit:
                    raise ProviderThrottled(f"local rate limit: {limit} calls per {window}s")
            self.calls.append(now)

    def remaining(self) -> dict[int, int]:
        now = self.clock()
        return {w: max(0, lim - sum(1 for t in self.calls if now - t < w)) for w, lim in self.limits.items()}


class TTLCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.data: dict[Any, tuple[float, Any]] = {}
        self.lock = threading.Lock()

    def get(self, key: Any, ttl: float) -> Any | None:
        with self.lock:
            hit = self.data.get(key)
            return hit[1] if hit and self.clock() - hit[0] < ttl else None

    def get_any(self, key: Any) -> Any | None:
        """Returns a value regardless of age (for explicit 'cached' fallback)."""
        hit = self.data.get(key)
        return hit[1] if hit else None

    def set(self, key: Any, value: Any) -> None:
        with self.lock:
            self.data[key] = (self.clock(), value)


def with_retries[T](
    fn: Callable[[], T], attempts: int = 3, base_delay: float = 1.0, sleep: Callable[[float], None] = time.sleep
) -> T:
    """Bounded retries with exponential backoff, only for retryable provider errors."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except ProviderError as e:
            if not e.retryable or attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("provider call failed (%s), retry %d/%d in %.1fs", e, attempt, attempts - 1, delay)
            sleep(delay)
    raise AssertionError("unreachable")

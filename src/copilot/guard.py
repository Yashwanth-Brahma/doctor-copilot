"""Protection for a public demo: per-visitor rate limits and a daily budget.

In memory, for one server instance (enough for a portfolio demo; a multi-instance deployment
would keep these counts in Redis or the database).
"""
import threading
import time
from collections import defaultdict, deque
from datetime import date


class RateLimiter:
    """At most `limit` requests per `window` seconds for each key (visitor IP)."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


class DailyBudget:
    """At most `limit` model-backed requests per day across all visitors."""

    def __init__(self, limit: int, today=date.today):
        self.limit, self.today = limit, today
        self.day, self.used = None, 0
        self.lock = threading.Lock()

    def try_spend(self) -> bool:
        with self.lock:
            if self.day != self.today():
                self.day, self.used = self.today(), 0
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


def client_ip(headers, fallback: str | None) -> str:
    """The visitor's IP. Behind Railway's proxy the real one is the first X-Forwarded-For entry."""
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return fallback or "unknown"

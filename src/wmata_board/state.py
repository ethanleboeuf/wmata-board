"""Last-known value of one feed, when it was fetched, and the last error."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class FeedState:
    value: Any = None
    fetched_at: float | None = None        # monotonic clock
    fetched_wall: datetime | None = None   # UTC, for display
    error: str | None = None
    error_kind: str | None = None

    def age(self, now: float) -> float | None:
        return None if self.fetched_at is None else max(0.0, now - self.fetched_at)

    def freshness(self, now: float, stale_after: float) -> dict:
        age = self.age(now)
        return {"age_s": None if age is None else int(age),
                "stale": age is not None and age > stale_after,
                "error": self.error_kind}

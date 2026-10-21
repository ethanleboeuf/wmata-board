"""One asyncio task per feed: cadence, demand gating, backoff.

A gated feed is fetched only while someone has asked for it in the last
`idle_after` seconds -- with the wall on skyview and no phone open, WMATA is
not called at all. `step()` is the whole fetch-and-record cycle and never
raises, so `run()` can loop forever; tests drive `step()` with a fake clock.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from .state import FeedState
from .wmata import WmataError

log = logging.getLogger("wmata_board.poller")


class Feed:
    def __init__(self, name: str, fetch: Callable[[], Awaitable[Any]], cadence: float, *,
                 gated: bool = True, idle_after: float = 90.0, max_backoff: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self.cadence = cadence
        self.state = FeedState()
        self.next_at = -math.inf
        self._fetch = fetch
        self._gated = gated
        self._idle_after = idle_after
        self._max_backoff = max_backoff
        self._clock = clock
        self._failures = 0
        self._wanted_until = -math.inf
        self._wake = asyncio.Event()
        self._updated = asyncio.Event()

    def wanted(self) -> bool:
        return not self._gated or self._clock() < self._wanted_until

    def want(self) -> bool:
        """Someone is looking. Returns True if the feed had gone idle."""
        was_idle = not self.wanted()
        self._wanted_until = self._clock() + self._idle_after
        self._wake.set()
        return was_idle

    def due(self) -> bool:
        return self._clock() >= self.next_at

    async def step(self) -> float:
        try:
            value = await self._fetch()
        except WmataError as exc:
            delay = self._failed(exc.kind, exc.message)
            log.warning("%s: %s (retry in %.0fs)", self.name, exc.message, delay)
        except Exception as exc:  # a parsing bug must not kill the feed
            delay = self._failed("internal", f"{type(exc).__name__}: {exc}")
            log.exception("%s: unexpected error (retry in %.0fs)", self.name, delay)
        else:
            if self._failures:
                log.info("%s: recovered", self.name)
            self._failures = 0
            self.state.value = value
            self.state.fetched_at = self._clock()
            self.state.fetched_wall = datetime.now(UTC)
            self.state.error = self.state.error_kind = None
            delay = self.cadence
        self.next_at = self._clock() + delay
        updated, self._updated = self._updated, asyncio.Event()
        updated.set()
        return delay

    def _failed(self, kind: str, message: str) -> float:
        self._failures += 1
        self.state.error, self.state.error_kind = message, kind
        return min(self.cadence * 2 ** self._failures, self._max_backoff)

    def update_event(self) -> asyncio.Event:
        """The event the next step() will set. Capture it synchronously, before
        any await, so a step that finishes in between cannot be missed."""
        return self._updated

    async def wait_for_update(self, timeout: float, event: asyncio.Event | None = None) -> bool:
        event = event if event is not None else self._updated
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return True
        except TimeoutError:
            return False

    async def run(self) -> None:
        while True:
            if not self.wanted():
                self._wake.clear()
                await self._wake.wait()
                continue
            wait = self.next_at - self._clock()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            await self.step()


class Poller:
    def __init__(self, feeds: Mapping[str, Feed]) -> None:
        self.feeds = dict(feeds)
        self._tasks: list[asyncio.Task] = []

    def __getitem__(self, name: str) -> Feed:
        return self.feeds[name]

    def start(self) -> None:
        self._tasks = [asyncio.create_task(f.run(), name=f"feed:{n}") for n, f in self.feeds.items()]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

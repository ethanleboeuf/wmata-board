import asyncio

import pytest

from wmata_board.poller import Feed, Poller
from wmata_board.state import FeedState
from wmata_board.wmata import WmataError


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(fetch, cadence=20.0, **kw):
    clock = Clock()
    return Feed("arrivals", fetch, cadence, clock=clock, **kw), clock


def test_freshness():
    s = FeedState()
    assert s.age(5.0) is None
    assert s.freshness(5.0, 60) == {"age_s": None, "stale": False, "error": None}
    s.fetched_at, s.error_kind = 0.0, "network"
    assert s.freshness(61.4, 60) == {"age_s": 61, "stale": True, "error": "network"}
    assert s.freshness(30.0, 60)["stale"] is False


async def test_success_stores_value_and_schedules_cadence():
    async def fetch():
        return 42

    feed, clock = make(fetch)
    assert await feed.step() == 20.0
    assert feed.state.value == 42
    assert feed.state.fetched_at == clock.t
    assert feed.state.fetched_wall is not None
    assert feed.state.error is None
    assert feed.next_at == clock.t + 20.0


async def test_backoff_doubles_and_caps_then_resets():
    outcome = {"fail": True}

    async def fetch():
        if outcome["fail"]:
            raise WmataError("network", "down")
        return "ok"

    feed, _ = make(fetch)
    delays = [await feed.step() for _ in range(5)]
    assert delays == [40.0, 80.0, 160.0, 300.0, 300.0]
    assert feed.state.error == "down" and feed.state.error_kind == "network"
    outcome["fail"] = False
    assert await feed.step() == 20.0
    assert feed.state.error is None and feed.state.error_kind is None


async def test_failure_keeps_last_good_value():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        if calls["n"] > 1:
            raise WmataError("rate_limited", "429")
        return "good"

    feed, _ = make(fetch)
    await feed.step()
    await feed.step()
    assert feed.state.value == "good"
    assert feed.state.error_kind == "rate_limited"


async def test_unexpected_exception_never_escapes():
    async def fetch():
        raise RuntimeError("bug")

    feed, _ = make(fetch)
    assert await feed.step() == 40.0
    assert feed.state.error_kind == "internal"


async def test_long_cadence_backoff_is_capped_below_cadence():
    async def fetch():
        raise WmataError("network", "down")

    feed, _ = make(fetch, cadence=86400.0)
    assert await feed.step() == 300.0


def test_demand_gating():
    async def fetch():
        return 1

    feed, clock = make(fetch, idle_after=90.0)
    assert not feed.wanted()
    assert feed.want() is True           # was idle
    assert feed.wanted()
    clock.t += 30
    assert feed.want() is False          # still wanted
    clock.t += 89
    assert feed.wanted()
    clock.t += 2
    assert not feed.wanted()


def test_ungated_always_wanted():
    async def fetch():
        return 1

    feed, _ = make(fetch, gated=False)
    assert feed.wanted()


async def test_due():
    async def fetch():
        return 1

    feed, clock = make(fetch)
    assert feed.due()
    await feed.step()
    assert not feed.due()
    clock.t += 20
    assert feed.due()


async def test_wait_for_update():
    async def fetch():
        return 1

    feed, _ = make(fetch)
    waiter = asyncio.create_task(feed.wait_for_update(1.0))
    await asyncio.sleep(0)
    await feed.step()
    assert await waiter is True
    assert await feed.wait_for_update(0.01) is False


async def test_run_loop_idles_until_wanted_then_polls():
    calls = []

    async def fetch():
        calls.append(1)
        return len(calls)

    feed = Feed("p", fetch, 0.02, idle_after=60.0)   # real clock
    poller = Poller({"p": feed})
    poller.start()
    await asyncio.sleep(0.05)
    assert calls == []                  # nobody asked
    feed.want()
    await asyncio.sleep(0.11)
    assert len(calls) >= 3
    assert poller["p"] is feed
    await poller.stop()
    n = len(calls)
    await asyncio.sleep(0.05)
    assert len(calls) == n              # stopped

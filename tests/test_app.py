import asyncio

import pytest
from fastapi.testclient import TestClient

from helpers import arrivals_state, config, incidents_state, station_state

from wmata_board.app import create_app
from wmata_board.fixtures import FixtureClient
from wmata_board.feeds import build_feeds
from wmata_board.poller import Feed


class Clock:
    t = 110.0

    def __call__(self):
        return self.t


@pytest.fixture
def app(fixtures):
    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), clock=clock)
    feeds["arrivals"].state = arrivals_state()
    feeds["incidents"].state = incidents_state()
    feeds["station"].state = station_state()
    return create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test",
                      fresh_wait_s=0, start_polling=False, clock=clock)


def test_board_endpoint(app):
    with TestClient(app) as c:
        r = c.get("/api/board")
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("no-store")
    body = r.json()
    assert body["station"]["name"] == "Court House"
    assert body["version"] == "test"
    assert len(body["platforms"]) == 2


def test_board_request_marks_feeds_wanted(app):
    feeds = app.state.feeds
    assert not feeds["arrivals"].wanted()
    with TestClient(app) as c:
        c.get("/api/board")
    assert feeds["arrivals"].wanted() and feeds["incidents"].wanted()


def test_healthz(app):
    with TestClient(app) as c:
        body = c.get("/healthz").json()
    assert body["ok"] is True
    assert body["api_key"] is True
    assert body["feeds"]["arrivals"] == {"age_s": 10, "error": None}
    assert set(body["feeds"]) >= {"arrivals", "incidents", "station"}


def test_index_served(app):
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


async def test_first_request_after_idle_waits_for_fresh_data(fixtures):
    """Review focus 3: switching to the board must not show stale minutes for 5 s."""
    cfg = config()
    calls = []

    async def slow_fetch():
        await asyncio.sleep(0.05)
        calls.append(1)
        return arrivals_state().value     # real trains, so no "closed" notice at night

    feeds = build_feeds(cfg, FixtureClient(fixtures))
    feeds["arrivals"] = Feed("arrivals", slow_fetch, 20.0)
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=2.0)
    import httpx
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            body = (await c.get("/api/board")).json()
    assert calls == [1]
    assert body["notice"] is None          # fetched before answering, not "Loading"

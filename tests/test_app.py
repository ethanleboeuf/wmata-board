import asyncio

import pytest
from fastapi.testclient import TestClient

from helpers import arrivals_state, config, incidents_state, station_state

from wmata_board.app import create_app
from wmata_board.fixtures import FixtureClient
from wmata_board.feeds import build_feeds
from wmata_board.network import FixtureNetwork
from wmata_board.poller import Feed


class Clock:
    t = 110.0

    def __call__(self):
        return self.t


@pytest.fixture
def app(fixtures):
    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), network_loader=FixtureNetwork(fixtures / "network.json"), clock=clock)
    feeds["arrivals"].state = arrivals_state()
    feeds["incidents"].state = incidents_state()
    feeds["station"].state = station_state()
    return create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test",
                      fresh_wait_s=0, start_polling=False, clock=clock,
                      wall_clock=lambda: 0.0)   # recorded feed timestamps are never 'old' here


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

    feeds = build_feeds(cfg, FixtureClient(fixtures), network_loader=FixtureNetwork(fixtures / "network.json"))
    feeds["arrivals"] = Feed("arrivals", slow_fetch, 20.0)
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=2.0)
    import httpx
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            body = (await c.get("/api/board")).json()
    assert calls == [1]
    assert body["notice"] is None          # fetched before answering, not "Loading"


async def _idle_app(fixtures, fetch):
    cfg = config()
    feeds = build_feeds(cfg, FixtureClient(fixtures), network_loader=FixtureNetwork(fixtures / "network.json"))
    feeds["arrivals"] = Feed("arrivals", fetch, 20.0)
    return create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=2.0)


async def test_instant_fetch_does_not_block_first_request(fixtures):
    """A fetch that never suspends finishes before the waiter starts; must not wait fresh_wait_s."""
    import time

    import httpx

    async def instant_fetch():
        return arrivals_state().value

    app = await _idle_app(fixtures, instant_fetch)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            t0 = time.monotonic()
            body = (await c.get("/api/board")).json()
            elapsed = time.monotonic() - t0
    assert elapsed < 1.0
    assert body["notice"] is None


async def test_concurrent_requests_at_idle_edge_both_get_fresh_data(fixtures):
    import httpx

    calls = []

    async def slow_fetch():
        await asyncio.sleep(0.05)
        calls.append(1)
        return arrivals_state().value

    app = await _idle_app(fixtures, slow_fetch)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r1, r2 = await asyncio.gather(c.get("/api/board"), c.get("/api/board"))
    assert calls == [1]
    assert r1.json()["notice"] is None and r2.json()["notice"] is None


def test_positions_endpoint(app, fixtures):
    from wmata_board.positions import decode_positions
    from helpers import state
    path = sorted((fixtures / "positions").glob("*.pb"))[0]
    app.state.feeds["positions"].state = state(decode_positions(path.read_bytes()))
    with TestClient(app) as c:
        body = c.get("/api/positions").json()
    assert body["stale"] is False and body["age_s"] == 10
    assert body["feed_timestamp"] > 0
    assert len(body["vehicles"]) > 20
    assert set(body["vehicles"][0]) == {"id", "line", "lat", "lon", "heading", "cars", "trip_id"}
    assert app.state.feeds["positions"].wanted()


def test_positions_before_first_fetch(app):
    with TestClient(app) as c:
        body = c.get("/api/positions").json()
    assert body == {"fetched_at": None, "feed_timestamp": None, "age_s": None, "stale": True,
                    "error": None, "vehicles": [], "ride": None}


def test_network_endpoint(app, fixtures):
    import json
    from helpers import state
    app.state.feeds["network"].state = state(json.loads((fixtures / "network.json").read_text(encoding="utf-8")))
    with TestClient(app) as c:
        body = c.get("/api/network").json()
    assert body["home"] == "K01"
    assert body["view"] == {"bbox": [-77.122, 38.844, -76.978, 38.966]}
    assert body["labels"][0] == "K04"
    assert body["places"][0] == {"name": "GEORGETOWN", "lat": 38.9085, "lon": -77.0665}
    assert body["landmarks"][0]["style"] == "hospital"
    assert set(body["lines"]) == {"RD", "OR", "SV", "BL", "GR", "YL"}


def test_network_loading(app):
    with TestClient(app) as c:
        r = c.get("/api/network")
    assert r.status_code == 503


def test_phone_served(app):
    with TestClient(app) as c:
        r = c.get("/phone")
    assert r.status_code == 200 and 'id="sheet"' in r.text


def test_positions_stale_when_feed_header_timestamp_is_old(fixtures):
    from wmata_board.positions import decode_positions
    from helpers import state
    cfg = config()
    clock = Clock()
    snap = decode_positions(sorted((fixtures / "positions").glob("*.pb"))[0].read_bytes())
    feeds = build_feeds(cfg, FixtureClient(fixtures), clock=clock)
    feeds["positions"].state = state(snap)            # fetched 10 s ago on our clock
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=0, start_polling=False,
                     clock=clock, wall_clock=lambda: snap.feed_timestamp + 600)
    with TestClient(app) as c:
        assert c.get("/api/positions").json()["stale"] is True
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=0, start_polling=False,
                     clock=clock, wall_clock=lambda: snap.feed_timestamp + 30)
    with TestClient(app) as c:
        assert c.get("/api/positions").json()["stale"] is False


def test_positions_zero_header_timestamp_falls_back_to_fetch_age(fixtures):
    from wmata_board.positions import PositionsSnapshot
    from helpers import state
    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), clock=clock)
    feeds["positions"].state = state(PositionsSnapshot(0, ()))
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=0, start_polling=False,
                     clock=clock, wall_clock=lambda: 1e12)
    with TestClient(app) as c:
        assert c.get("/api/positions").json()["stale"] is False


@pytest.fixture
def commute_app(fixtures):
    from zoneinfo import ZoneInfo

    from wmata_board.trips import FixtureSchedule

    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), clock=clock,
                        schedule_loader=FixtureSchedule(fixtures / "schedule.json", ZoneInfo(cfg.board.timezone)))
    feeds["schedule"].state.value = asyncio.run(feeds["schedule"]._fetch())
    return create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test",
                      fresh_wait_s=0, start_polling=False, clock=clock)


def test_commute_outside_the_windows_does_not_poll(commute_app):
    with TestClient(commute_app) as c:
        body = c.get("/api/commute?at=12:00").json()
    assert body["mode"] is None
    assert not commute_app.state.feeds["trips"].wanted()


def test_commute_morning_preview_from_the_timetable(commute_app):
    with TestClient(commute_app) as c:
        r = c.get("/api/commute?mode=am&at=7:30")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("no-store")
    body = r.json()
    assert body["mode"] == "am" and body["live"] is False and body["wall_platform"] == "2"
    rows = body["am"]["rows"]
    assert len(rows) == 5
    assert all(r["line"] in ("OR", "SV") for r in rows)
    assert any(r["target"] for r in rows)
    assert not commute_app.state.feeds["trips"].wanted()   # a preview at another time ignores live data


def test_commute_now_marks_live_trips_wanted(commute_app):
    with TestClient(commute_app) as c:
        assert c.get("/api/commute?mode=am").json()["mode"] == "am"
    assert commute_app.state.feeds["trips"].wanted()


def test_commute_evening_preview(commute_app):
    with TestClient(commute_app) as c:
        body = c.get("/api/commute?mode=pm&at=17:00").json()
    assert body["pm"]["station_name"] == "Takoma"
    assert len(body["pm"]["hospital"]) == 5 and len(body["pm"]["station"]) == 5


@pytest.mark.parametrize("query", ["mode=noon", "at=25:00", "at=7"])
def test_commute_rejects_bad_preview_params(commute_app, query):
    with TestClient(commute_app) as c:
        assert c.get(f"/api/commute?{query}").status_code == 422


def test_phone_page_is_installable(app):
    with TestClient(app) as c:
        r = c.get("/manifest.webmanifest")
        page = c.get("/phone").text
        icons = [c.get(i["src"]) for i in r.json()["icons"]]
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["start_url"] == "/phone" and r.json()["display"] == "standalone"
    assert all(i.status_code == 200 and i.content[:4] == b"\x89PNG" for i in icons)
    assert 'rel="manifest" href="/manifest.webmanifest"' in page
    assert 'rel="apple-touch-icon" href="/static/icons/icon-180.png"' in page


@pytest.fixture
def trip_app(fixtures):
    """Live trips, positions and timetable from the same recording, with the
    wall clock pinned to it so the live feed counts as fresh."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from wmata_board.trips import FixtureSchedule, decode_trip_updates

    cfg = config()
    clock = Clock()
    client = FixtureClient(fixtures)
    feeds = build_feeds(cfg, client, clock=clock, network_loader=FixtureNetwork(fixtures / "network.json"),
                        schedule_loader=FixtureSchedule(fixtures / "schedule.json", ZoneInfo(cfg.board.timezone)))
    for name in ("schedule", "network", "positions"):
        feeds[name].state.value = asyncio.run(feeds[name]._fetch())
    upd = decode_trip_updates((fixtures / "trip_updates.pb").read_bytes())
    # FixtureSchedule replays as today; the wall clock here is the recording's day
    day = datetime.fromtimestamp(upd.feed_timestamp, ZoneInfo(cfg.board.timezone)).strftime("%Y%m%d")
    sched = feeds["schedule"].state.value
    sched["services"] = {sid: [day] for sid in sched["services"]}
    feeds["trips"].state.value, feeds["trips"].state.fetched_at = upd, clock.t
    app = create_app(cfg, client, feeds=feeds, version="test", fresh_wait_s=0, start_polling=False,
                     clock=clock, wall_clock=lambda: float(upd.feed_timestamp))
    app.state.updates = upd
    return app


def test_trip_endpoint_live(trip_app):
    vehicles = trip_app.state.feeds["positions"].state.value.vehicles
    v = next(v for v in vehicles if v.line == "RD" and v.trip_id in trip_app.state.updates.trips
             and len(trip_app.state.updates.trips[v.trip_id].stops) >= 3)
    with TestClient(trip_app) as c:
        r = c.get(f"/api/trip/{v.trip_id}")
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"].startswith("no-store")
    assert body["live"] is True and body["line"] == "RD" and body["cars"] == v.cars
    assert body["destination"] and len(body["stops"]) >= 2
    assert all(s["name"] != s["code"] for s in body["stops"])   # names from the network
    assert trip_app.state.feeds["trips"].wanted()


def test_trip_endpoint_timetable_preview_and_404(trip_app):
    with TestClient(trip_app) as c:
        row = c.get("/api/commute?mode=am&at=7:20").json()["am"]["rows"][0]
        leg = row["legs"][0]
        body = c.get(f"/api/trip/{leg['trip']}?at=7:20").json()
        missing = c.get("/api/trip/no-such-trip")
    assert body["live"] is False and body["line"] == leg["line"]
    assert [s["code"] for s in body["stops"]][:2] == ["K01", "C01"]
    assert missing.status_code == 404 and missing.json() == {"error": "unknown trip"}


def test_ride_is_shared_through_positions(fixtures, tmp_path):
    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), network_loader=FixtureNetwork(fixtures / "network.json"), clock=clock)
    now = [1000.0]
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test", fresh_wait_s=0,
                     start_polling=False, clock=clock, wall_clock=lambda: now[0], data_dir=tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/ride").json() == {"ride": None, "trip": None}
        assert c.put("/api/ride", json={"trips": ["a/b"], "until": 2000}).status_code == 400
        assert c.put("/api/ride", json={"trips": ["or1"], "until": 99999}).status_code == 400
        r = c.put("/api/ride", json={"trips": ["or1", "rd2"], "switch_at": 1500, "until": 2000})
        assert r.json()["trip"] == "or1"
        assert c.get("/api/positions").json()["ride"] == "or1"
        now[0] = 1600.0
        assert c.get("/api/positions").json()["ride"] == "rd2"
    # a restart keeps it
    again = create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test", fresh_wait_s=0,
                       start_polling=False, clock=clock, wall_clock=lambda: now[0], data_dir=tmp_path)
    with TestClient(again) as c:
        assert c.get("/api/ride").json()["trip"] == "rd2"
        assert c.delete("/api/ride").json() == {"ride": None, "trip": None}
        now[0] = 2100.0
    assert not (tmp_path / "ride.json").exists()


def test_board_for_another_station(app, fixtures):
    from wmata_board.state import FeedState

    net = asyncio.run(FixtureNetwork(fixtures / "network.json").load())
    app.state.feeds["network"].state = FeedState(value=net, fetched_at=100.0)
    with TestClient(app) as c:
        assert c.get("/api/board").json()["station"]["code"] == "K01"
        b = c.get("/api/board?station=C01").json()
        assert b["station"] == {"code": "A01", "name": "Metro Center", "home": False}
        assert c.get("/api/board?station=Z99").status_code == 404
        assert c.get("/api/board?station=k01").status_code == 422

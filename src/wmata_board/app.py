"""HTTP front end: JSON endpoints, the two pages, static files.

Deliberately thin -- all decisions live in board.py and the pure modules.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .board import build_board
from .commute import AM, PM, RideMemory, build_commute, commute_mode, commute_stations, get_off_stations, live_updates
from .config import Config
from .feeds import build_feeds
from .poller import Feed, Poller
from .positions import POSITIONS_STALE_AFTER_S
from .ride import load_ride, moved_ride, parse_ride, ride_trip, ride_trips, save_ride
from .state import FeedState
from .tripinfo import station_names, trip_detail
from .trips import scheduled_trips

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
DATA_DIR = PROJECT_ROOT / "data"
NO_STORE = {"Cache-Control": "no-store, must-revalidate"}
AT_PATTERN = r"^([01]?\d|2[0-3]):[0-5]\d$"   # ?at=H:MM previews


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
BASEMAP_HEADERS = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}


def range_response(path: Path, range_header: str | None, method: str) -> Response:
    """Byte-range file serving for the pmtiles protocol (it reads by range)."""
    size = path.stat().st_size
    if not range_header:
        if method == "HEAD":
            return Response(headers={**BASEMAP_HEADERS, "Content-Length": str(size)},
                            media_type="application/octet-stream")
        return FileResponse(path, media_type="application/octet-stream", headers=BASEMAP_HEADERS)
    m = _RANGE_RE.match(range_header.strip())
    start = end = None
    if m and (m[1] or m[2]):
        if m[1]:
            start = int(m[1])
            end = min(int(m[2]), size - 1) if m[2] else size - 1
        else:
            start, end = max(0, size - int(m[2])), size - 1
    if start is None or start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with path.open("rb") as f:
        f.seek(start)
        body = f.read(end - start + 1)
    return Response(body, status_code=206, media_type="application/octet-stream",
                    headers={**BASEMAP_HEADERS, "Content-Range": f"bytes {start}-{end}/{size}"})


class _NoStoreStaticFiles(StaticFiles):
    """What is on screen must match what is on disk after a deploy."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


def create_app(config: Config, client, *, feeds: dict[str, Feed] | None = None,
               version: str = __version__, fresh_wait_s: float = 3.0,
               start_polling: bool = True, data_dir: Path = DATA_DIR,
               network_loader=None, schedule_loader=None,
               clock: Callable[[], float] = time.monotonic,
               wall_clock: Callable[[], float] = time.time) -> FastAPI:
    feeds = feeds if feeds is not None else build_feeds(config, client, network_loader=network_loader,
                                                       schedule_loader=schedule_loader, clock=clock)
    poller = Poller(feeds)
    tz = ZoneInfo(config.board.timezone)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_polling:
            poller.start()
        try:
            yield
        finally:
            await poller.stop()
            await client.aclose()

    app = FastAPI(title="wmata-board", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.feeds = feeds
    app.state.data_dir = data_dir
    ride_path = data_dir / "ride.json"
    app.state.ride = load_ride(ride_path)
    ride_memory = RideMemory()   # the ride's passed stops, for its pinned commute row

    async def want(*names: str) -> None:
        """Mark feeds wanted; if one is due (about to fetch, or fetching now --
        next_at only advances when a step finishes), wait briefly for that
        fetch so the first screen after idle is fresh. The event is captured
        before any await so a fetch that finishes immediately is not missed."""
        waits = []
        for name in names:
            feed = feeds[name]
            feed.want()
            if feed.due() and fresh_wait_s > 0:
                waits.append(feed.wait_for_update(fresh_wait_s, feed.update_event()))
        if waits:
            await asyncio.gather(*waits)

    @app.get("/api/board")
    async def board(station: str | None = Query(None, pattern=r"^[A-Z]\d{2}$")):
        """`station`: any station code (the phone's picker); home when omitted."""
        other = None
        if station and station != config.board.station:
            net = feeds["network"].state.value if "network" in feeds else None
            other = next((s for s in (net or {}).get("stations", []) if station in s["codes"]), None)
            if other is None:
                return JSONResponse({"error": "unknown station"}, status_code=404, headers=NO_STORE)
        await want("arrivals", "incidents")
        body = build_board(config=config, arrivals=feeds["arrivals"].state,
                           incidents=feeds["incidents"].state, station=feeds["station"].state,
                           now=clock(), now_local=datetime.now(tz), version=version, other=other)
        return JSONResponse(body, headers=NO_STORE)

    @app.get("/api/positions")
    async def positions():
        await want("positions")
        st = feeds["positions"].state
        age = st.age(clock())
        snap = st.value
        feed_ts = snap.feed_timestamp if snap else 0
        feed_old = bool(feed_ts) and wall_clock() - feed_ts > POSITIONS_STALE_AFTER_S
        return JSONResponse({
            "fetched_at": st.fetched_wall.isoformat(timespec="seconds") if st.fetched_wall else None,
            "feed_timestamp": snap.feed_timestamp if snap else None,
            "age_s": None if age is None else int(age),
            "stale": age is None or age > POSITIONS_STALE_AFTER_S or feed_old,
            "error": st.error_kind,
            "vehicles": [v.as_json() for v in snap.vehicles] if snap else [],
            "ride": ride_trip(app.state.ride, wall_clock()),
        }, headers=NO_STORE)

    # The easter egg: the phone's "I'm on this one" (see ride.py).
    def ride_body() -> JSONResponse:
        ride, now = app.state.ride, wall_clock()
        current = ride_trip(ride, now)
        return JSONResponse({"ride": ride.as_json() if current else None, "trip": current}, headers=NO_STORE)

    @app.get("/api/ride")
    async def get_ride():
        return ride_body()

    @app.put("/api/ride")
    async def put_ride(request: Request):
        try:
            ride = parse_ride(await request.json(), wall_clock())
        except ValueError as err:
            return JSONResponse({"error": str(err)}, status_code=400, headers=NO_STORE)
        app.state.ride = ride
        save_ride(ride_path, ride)
        return ride_body()

    @app.delete("/api/ride")
    async def delete_ride():
        app.state.ride = None
        save_ride(ride_path, None)
        return ride_body()

    @app.get("/api/commute")
    async def commute(mode: str | None = Query(None, pattern=f"^({AM}|{PM})$"),
                      at: str | None = Query(None, pattern=AT_PATTERN)):
        """`mode` and `at` (H:MM today) are for previewing a panel off-hours. A
        preview at another time plans on the timetable alone: the live feed
        describes now, and would drop that time's trains as not running."""
        cfg = config.commute
        if cfg is None:
            return JSONResponse({"mode": None}, headers=NO_STORE)
        wall_now = wall_clock()
        now = preview_time(wall_now, at)
        riding = None if at else ride_trips(app.state.ride, wall_now)
        if mode or riding or commute_mode(cfg, datetime.fromtimestamp(now, tz)):
            await want(*(("incidents",) if at else ("trips", "incidents")))
        sched = feeds.get("schedule")
        body = build_commute(cfg, schedule=sched.state if sched else FeedState(),
                             updates=FeedState() if at else feeds["trips"].state, tz=tz, now=now, now_mono=clock(),
                             wall_now=wall_now, mode=mode, incidents=feeds["incidents"].state,
                             ride=riding, memory=ride_memory)
        if (moved := ride_memory.rebooked) is not None:   # she missed a connection: the rider moves too
            ride_memory.rebooked = None
            if app.state.ride is not None and app.state.ride.trips == riding:
                app.state.ride = moved_ride(app.state.ride, moved.trips, moved.switch_at, moved.arrive)
                save_ride(ride_path, app.state.ride)
        return JSONResponse(body, headers=NO_STORE)

    def preview_time(wall_now: float, at: str | None) -> float:
        if not at:
            return wall_now
        h, m = (int(x) for x in at.split(":"))
        return datetime.fromtimestamp(wall_now, tz).replace(hour=h, minute=m, second=0, microsecond=0).timestamp()

    @app.get("/api/trip/{trip_id}")
    async def trip(trip_id: str, at: str | None = Query(None, pattern=AT_PATTERN)):
        """One train for the phone's tap card. `at` (a commute preview) uses the
        timetable alone, like /api/commute."""
        wall_now = wall_clock()
        now = preview_time(wall_now, at)
        trips_feed = feeds.get("trips")
        if trips_feed is not None and not at:
            await want("trips")
        live = None if at or trips_feed is None else live_updates(trips_feed.state, clock(), wall_now)
        sched_feed, net_feed = feeds.get("schedule"), feeds.get("network")
        schedule = sched_feed.state.value if sched_feed else None
        scheduled = [t for t, _ in scheduled_trips(schedule, datetime.fromtimestamp(now, tz).date(), tz)] if schedule else []
        detail = trip_detail(trip_id, live=live, scheduled=scheduled,
                             names=station_names(net_feed.state.value if net_feed else None, schedule),
                             positions=feeds["positions"].state.value, now=now, tz=tz,
                             mine=commute_stations(config.commute) if config.commute else (),
                             off=get_off_stations(config.commute, datetime.fromtimestamp(now, tz)) if config.commute else ())
        if detail is None:
            return JSONResponse({"error": "unknown trip"}, status_code=404, headers=NO_STORE)
        return JSONResponse(detail, headers=NO_STORE)

    @app.get("/api/network")
    async def network():
        feed = feeds.get("network")
        net = feed.state.value if feed else None
        if net is None:
            return JSONResponse({"error": "network loading"}, status_code=503, headers=NO_STORE)
        m = config.map
        return JSONResponse({
            **net,
            "home": config.board.station,
            "view": {"bbox": list(m.bbox)},
            "labels": list(m.labels),
            "places": [{"name": p.name, "lat": p.lat, "lon": p.lon} for p in m.places],
            "landmarks": [{"name": x.name, "lat": x.lat, "lon": x.lon, "style": x.style} for x in m.landmarks],
            "theme": m.theme,
            "wave": m.wave and {"lat": m.wave.lat, "lon": m.wave.lon, "message": m.wave.message,
                              "cheer": m.wave.cheer},
        }, headers={"Cache-Control": "max-age=600"})

    @app.get("/healthz")
    async def healthz():
        now = clock()
        return JSONResponse({
            "ok": True, "version": version, "api_key": config.api_key is not None,
            "feeds": {name: {"age_s": None if (a := f.state.age(now)) is None else int(a),
                             "error": f.state.error_kind} for name, f in feeds.items()},
        }, headers=NO_STORE)

    @app.api_route("/basemap.pmtiles", methods=["GET", "HEAD"])
    def basemap(request: Request):
        path = data_dir / "basemap.pmtiles"
        if not path.is_file():
            return JSONResponse({"error": "basemap not built; run tools/build_basemap.sh"}, status_code=404)
        return range_response(path, request.headers.get("range"), request.method)

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html", headers=NO_STORE)

    @app.get("/phone")
    async def phone():
        return FileResponse(WEB_DIR / "phone.html", headers=NO_STORE)

    @app.get("/manifest.webmanifest")
    async def manifest():
        """Home-screen install for the phone page. Served with an explicit type:
        Windows' mimetype table doesn't know .webmanifest."""
        return FileResponse(WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json",
                            headers=NO_STORE)

    app.mount("/static", _NoStoreStaticFiles(directory=WEB_DIR), name="static")
    return app

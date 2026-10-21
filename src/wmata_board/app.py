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

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .board import build_board
from .config import Config
from .feeds import build_feeds
from .poller import Feed, Poller
from .positions import POSITIONS_STALE_AFTER_S

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
DATA_DIR = PROJECT_ROOT / "data"
NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


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
               network_loader=None,
               clock: Callable[[], float] = time.monotonic) -> FastAPI:
    feeds = feeds if feeds is not None else build_feeds(config, client, network_loader=network_loader, clock=clock)
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
    async def board():
        await want("arrivals", "incidents")
        body = build_board(config=config, arrivals=feeds["arrivals"].state,
                           incidents=feeds["incidents"].state, station=feeds["station"].state,
                           now=clock(), now_local=datetime.now(tz), version=version)
        return JSONResponse(body, headers=NO_STORE)

    @app.get("/api/positions")
    async def positions():
        await want("positions")
        st = feeds["positions"].state
        age = st.age(clock())
        snap = st.value
        return JSONResponse({
            "fetched_at": st.fetched_wall.isoformat(timespec="seconds") if st.fetched_wall else None,
            "feed_timestamp": snap.feed_timestamp if snap else None,
            "age_s": None if age is None else int(age),
            "stale": age is None or age > POSITIONS_STALE_AFTER_S,
            "error": st.error_kind,
            "vehicles": [v.as_json() for v in snap.vehicles] if snap else [],
        }, headers=NO_STORE)

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

    app.mount("/static", _NoStoreStaticFiles(directory=WEB_DIR), name="static")
    return app

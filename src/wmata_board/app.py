"""HTTP front end: JSON endpoints, the two pages, static files.

Deliberately thin -- all decisions live in board.py and the pure modules.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
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


class _NoStoreStaticFiles(StaticFiles):
    """What is on screen must match what is on disk after a deploy."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


def create_app(config: Config, client, *, feeds: dict[str, Feed] | None = None,
               version: str = __version__, fresh_wait_s: float = 3.0,
               start_polling: bool = True, data_dir: Path = DATA_DIR,
               clock: Callable[[], float] = time.monotonic) -> FastAPI:
    feeds = feeds if feeds is not None else build_feeds(config, client, clock=clock)
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

    @app.get("/healthz")
    async def healthz():
        now = clock()
        return JSONResponse({
            "ok": True, "version": version, "api_key": config.api_key is not None,
            "feeds": {name: {"age_s": None if (a := f.state.age(now)) is None else int(a),
                             "error": f.state.error_kind} for name, f in feeds.items()},
        }, headers=NO_STORE)

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html", headers=NO_STORE)

    app.mount("/static", _NoStoreStaticFiles(directory=WEB_DIR), name="static")
    return app

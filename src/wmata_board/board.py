"""Assemble the /api/board payload from feed states. Pure.

The server decides what the arrivals panel should say (`notice`) so the wall
and phone pages stay dumb: when `notice` is set they show it instead of rows.
"""

from __future__ import annotations

from datetime import datetime

from .config import Config
from .incidents import alerts_for
from .predictions import platforms_for
from .service import ServiceStatus, StationData, service_status
from .state import FeedState
from .wmata import WmataError

STALE_AFTER_S = 60.0
INCIDENTS_STALE_AFTER_S = 180.0
UNAVAILABLE_AFTER_S = 600.0
INCIDENTS_EXPIRE_AFTER_S = 900.0

NOTICE_NO_KEY = "No WMATA API key configured"
NOTICE_BAD_KEY = "WMATA rejected the API key"
NOTICE_LOADING = "Loading arrivals…"
NOTICE_UNAVAILABLE = "Live arrivals unavailable"
NOTICE_NO_TRAINS = "No trains predicted"


def effective_lines(config: Config, station: StationData | None) -> tuple[str, ...] | None:
    if config.board.lines:
        return config.board.lines
    if station is not None and station.lines:
        return station.lines
    return None


def _service(station: StationData | None, now_local: datetime) -> ServiceStatus | None:
    if station is None:
        return None
    try:
        return service_status(station.times, station.code, now_local)
    except WmataError:
        return None


def _notice(config: Config, arrivals: FeedState, age: float | None, has_trains: bool,
            service: ServiceStatus | None) -> str | None:
    if config.api_key is None:
        return NOTICE_NO_KEY
    rejected = arrivals.error_kind == "api_key"
    if rejected and (arrivals.value is None or (age is not None and age > STALE_AFTER_S)):
        return NOTICE_BAD_KEY
    if arrivals.value is None:
        return NOTICE_UNAVAILABLE if arrivals.error else NOTICE_LOADING
    if age is not None and age > UNAVAILABLE_AFTER_S:
        return NOTICE_UNAVAILABLE
    if not has_trains and service is not None and not service.in_service and service.resumes:
        return f"No trains · service resumes {service.resumes}"
    return None


def build_board(*, config: Config, arrivals: FeedState, incidents: FeedState, station: FeedState,
                now: float, now_local: datetime, version: str, other: dict | None = None) -> dict:
    """`other`: a network station ({"codes", "name"}) to show instead of the
    home one (the phone's picker). It gets every line, the default platform
    labels, all of a transfer station's platforms, and no first/last train."""
    if other is None:
        codes = (config.board.station,)
        info: StationData | None = station.value
        lines = effective_lines(config, info)
        service = _service(info, now_local)
        name = info.name if info else codes[0]
    else:
        codes, name, lines, service = tuple(other["codes"]), other["name"], None, None

    trains = [t for t in (arrivals.value or []) if t.station in codes and (lines is None or t.line in lines)]
    age = arrivals.age(now)
    notice = _notice(config, arrivals, age, bool(trains), service)
    if notice in (NOTICE_NO_KEY, NOTICE_BAD_KEY, NOTICE_UNAVAILABLE, NOTICE_LOADING):
        trains = []
    elif notice is None and other is not None and not trains:
        notice = NOTICE_NO_TRAINS

    platforms = [p for c in codes for p in platforms_for(trains, c, config.platforms.get(c, {}),
                                                         config.board.rows_per_direction)]
    if other is not None:   # alerts for the lines seen here (all of them when none are)
        lines = tuple(sorted({t.line for t in trains})) or None
    incidents_age = incidents.age(now)
    expired = incidents_age is not None and incidents_age > INCIDENTS_EXPIRE_AFTER_S
    alerts = [] if expired else alerts_for(incidents.value or [], lines)

    return {
        "station": {"code": codes[0], "name": name, "home": other is None},
        "timezone": config.board.timezone,
        "generated_at": now_local.isoformat(timespec="seconds"),
        "version": version,
        "platforms": [p.as_json() for p in platforms],
        "notice": notice,
        "alerts": [a.as_json() for a in alerts],
        "service": service.as_json() if service else None,
        "freshness": {
            "arrivals": arrivals.freshness(now, STALE_AFTER_S),
            "incidents": incidents.freshness(now, INCIDENTS_STALE_AFTER_S),
        },
    }

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

NOTICE_NO_KEY = "No WMATA API key configured"
NOTICE_BAD_KEY = "WMATA rejected the API key"
NOTICE_LOADING = "Loading arrivals…"
NOTICE_UNAVAILABLE = "Live arrivals unavailable"


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
    if arrivals.value is None:
        if arrivals.error_kind == "api_key":
            return NOTICE_BAD_KEY
        return NOTICE_UNAVAILABLE if arrivals.error else NOTICE_LOADING
    if age is not None and age > UNAVAILABLE_AFTER_S:
        return NOTICE_UNAVAILABLE
    if not has_trains and service is not None and not service.in_service and service.resumes:
        return f"No trains · service resumes {service.resumes}"
    return None


def build_board(*, config: Config, arrivals: FeedState, incidents: FeedState, station: FeedState,
                now: float, now_local: datetime, version: str) -> dict:
    code = config.board.station
    info: StationData | None = station.value
    lines = effective_lines(config, info)

    trains = [t for t in (arrivals.value or []) if t.station == code and (lines is None or t.line in lines)]
    service = _service(info, now_local)
    age = arrivals.age(now)
    notice = _notice(config, arrivals, age, bool(trains), service)
    if notice in (NOTICE_NO_KEY, NOTICE_BAD_KEY, NOTICE_UNAVAILABLE, NOTICE_LOADING):
        trains = []

    platforms = platforms_for(trains, code, config.platforms.get(code, {}),
                              config.board.rows_per_direction)
    alerts = alerts_for(incidents.value or [], lines)

    return {
        "station": {"code": code, "name": info.name if info else code},
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

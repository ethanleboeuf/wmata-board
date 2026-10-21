"""Station facts from jStationInfo / jStationTimes, and whether the station is
in service right now. Pure.

A service day starts at 04:00: WMATA lists the last trains as clock times, and
"00:20" (or "02:20" on Friday and Saturday nights) belongs to the evening
before. jStationTimes' OpeningTime is not trusted -- Saturday's says 07:10
while its first train is at 06:14 -- so the window is the earliest first train
to the latest last train.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from .wmata import WmataError

SERVICE_DAY_STARTS = time(4, 0)
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True, slots=True)
class StationData:
    code: str
    name: str
    lines: tuple[str, ...]
    times: Any


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    first_train: str
    last_train: str
    in_service: bool
    resumes: str | None

    def as_json(self) -> dict:
        return {"first_train": self.first_train, "last_train": self.last_train}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def station_data(code: str, info: Any, times: Any) -> StationData:
    info = info if isinstance(info, Mapping) else {}
    lines = tuple(x for k in ("LineCode1", "LineCode2", "LineCode3", "LineCode4")
                  if (x := _text(info.get(k)).upper()))
    return StationData(code, _text(info.get("Name")) or code, lines, times)


def clock_label(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _entry(payload: Any, station: str) -> Mapping[str, Any]:
    entries = payload.get("StationTimes") if isinstance(payload, Mapping) else None
    for e in entries or []:
        if isinstance(e, Mapping) and e.get("Code") == station:
            return e
    raise WmataError("parse", f"no station times for {station}")


def _window(entry: Mapping[str, Any], day: date, now: datetime) -> tuple[datetime, datetime] | None:
    sched = entry.get(_DAYS[day.weekday()])
    if not isinstance(sched, Mapping):
        return None

    def at(hhmm: str) -> datetime:
        t = time.fromisoformat(hhmm)
        d = day + timedelta(days=1) if t < SERVICE_DAY_STARTS else day
        return datetime.combine(d, t, now.tzinfo)

    def times(key: str) -> list[datetime]:
        out = []
        for item in sched.get(key) or []:
            try:
                out.append(at(_text(item.get("Time"))))
            except (AttributeError, ValueError):
                continue
        return out

    firsts, lasts = times("FirstTrains"), times("LastTrains")
    if not firsts or not lasts:
        return None
    return min(firsts), max(lasts)


def service_status(times_payload: Any, station: str, now: datetime) -> ServiceStatus | None:
    entry = _entry(times_payload, station)
    service_day = (now - timedelta(hours=SERVICE_DAY_STARTS.hour)).date()
    window = _window(entry, service_day, now)
    if window is None:
        return None
    first, last = window
    if first <= now <= last:
        return ServiceStatus(clock_label(first), clock_label(last), True, None)
    if now < first:
        resumes: datetime | None = first
    else:
        nxt = _window(entry, service_day + timedelta(days=1), now)
        resumes = nxt[0] if nxt else None
    return ServiceStatus(clock_label(first), clock_label(last), False,
                         clock_label(resumes) if resumes else None)

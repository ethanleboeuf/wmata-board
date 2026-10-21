"""Trips with their times at the commute's stations: timetable + live. Pure.

Two sources, merged by trip_id (they share ids):

- the GTFS static timetable, reduced by `build_schedule` to the trips that
  call at two or more of the stations we care about;
- GTFS-RT trip updates (`decode_trip_updates`), which predict every
  not-yet-passed stop of each running trip, and of trips starting within
  ~40 min (so 70-90 min ahead at a given station).

`merge_trips` overlays the live predictions on today's timetable. A live trip
lists only its future stops, so a timetabled stop it no longer lists has been
passed. Stops without a time (NO_DATA) get the delay of the nearest earlier
predicted stop. Measured 2026-10-21: the live feed carries ~97% of running
trips and nearly every trip starting within 30 min, so while it is fresh a
timetabled trip it does not list that should already be running (or starts
within LIVE_HORIZON_S) is taken as not running.

Station codes come from platform stop_ids ("PF_A01_1" -> "A01"): Metro
Center's Red platform is A01 and its Orange/Silver/Blue platform C01.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .lines import ROUTE_LINES
from .wmata import WmataError

_PLATFORM_RE = re.compile(r"^PF_([A-Z]\d{2})_")
LIVE_HORIZON_S = 1200.0

_TD = gtfs_realtime_pb2.TripDescriptor
_STU = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate
_GONE = {_TD.CANCELED, _TD.DELETED}


def station_code(stop_id: str) -> str | None:
    m = _PLATFORM_RE.match(stop_id)
    return m[1] if m else None


@dataclass(frozen=True, slots=True)
class Stop:
    code: str
    arrive: float    # epoch seconds
    depart: float


@dataclass(frozen=True, slots=True)
class Trip:
    id: str
    line: str
    stops: tuple[Stop, ...]    # in calling order
    live: bool


# ---- live ------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LiveTrip:
    id: str
    line: str
    gone: bool                                         # cancelled / deleted
    stops: tuple[tuple[str, float | None, float | None], ...]   # (code, arrive, depart); None: no data
    skipped: frozenset[str]


@dataclass(frozen=True, slots=True)
class TripUpdates:
    feed_timestamp: int
    trips: dict[str, LiveTrip]


def decode_trip_updates(data: bytes, stations: Iterable[str]) -> TripUpdates:
    wanted = set(stations)
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(data)
    except DecodeError:
        raise WmataError("parse", "bad GTFS-RT trip updates") from None
    trips = {}
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        line = ROUTE_LINES.get(tu.trip.route_id)
        if not tu.trip.trip_id or line is None:
            continue
        stops, skipped = [], set()
        for s in tu.stop_time_update:
            code = station_code(s.stop_id)
            if code not in wanted:
                continue
            if s.schedule_relationship == _STU.SKIPPED:
                skipped.add(code)
                continue
            arr = s.arrival.time or s.departure.time or None
            dep = s.departure.time or s.arrival.time or None
            stops.append((code, arr and float(arr), dep and float(dep)))
        trips[tu.trip.trip_id] = LiveTrip(tu.trip.trip_id, line, tu.trip.schedule_relationship in _GONE,
                                          tuple(stops), frozenset(skipped))
    return TripUpdates(int(feed.header.timestamp), trips)


# ---- timetable ---------------------------------------------------------------

def _rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))


def _seconds(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def build_schedule(data: bytes, stations: Iterable[str]) -> dict:
    """{"stations", "names": {code: name}, "services": {service_id: [YYYYMMDD]},
    "trips": [[trip_id, service_id, line, start_s, [[code, arr_s, dep_s], ...]]]}.
    Times are GTFS seconds after the service day's midnight (may pass 24 h).
    WMATA publishes service days in calendar_dates.txt only."""
    wanted = set(stations)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        services: dict[str, list[str]] = defaultdict(list)
        for r in _rows(z, "calendar_dates.txt"):
            if r["exception_type"] == "1":
                services[r["service_id"]].append(r["date"])
        trips = {r["trip_id"]: (r["service_id"], ROUTE_LINES[r["route_id"]])
                 for r in _rows(z, "trips.txt") if r["route_id"] in ROUTE_LINES}
        start: dict[str, int] = {}
        calls: dict[str, list[tuple[int, str, int, int]]] = defaultdict(list)
        for r in _rows(z, "stop_times.txt"):
            tid = r["trip_id"]
            if tid not in trips:
                continue
            dep = _seconds(r["departure_time"])
            start[tid] = min(start.get(tid, dep), dep)
            code = station_code(r["stop_id"])
            if code in wanted:
                calls[tid].append((int(r["stop_sequence"]), code, _seconds(r["arrival_time"]), dep))
        names = {}   # combined ids like STN_A01_C01 name both codes
        for s in _rows(z, "stops.txt"):
            if s.get("location_type") == "1" and s["stop_id"].startswith("STN_"):
                for code in s["stop_id"][4:].split("_"):
                    names[code] = s["stop_name"]
    out = []
    for tid, seq in calls.items():
        if len(seq) >= 2:
            sid, line = trips[tid]
            out.append([tid, sid, line, start[tid], [[c, a, d] for _, c, a, d in sorted(seq)]])
    used = {t[1] for t in out}
    return {"stations": sorted(wanted), "names": {c: names[c] for c in sorted(wanted) if c in names},
            "services": {sid: sorted(ds) for sid, ds in services.items() if sid in used},
            "trips": sorted(out)}


def _midnight(day: date, tz: ZoneInfo) -> float:
    return datetime.combine(day, dtime(0, 0), tz).timestamp()


def scheduled_trips(schedule: dict, day: date, tz: ZoneInfo) -> list[tuple[Trip, float]]:
    """The day's timetabled trips, each with its start time (epoch)."""
    ymd = day.strftime("%Y%m%d")
    active = {sid for sid, dates in schedule["services"].items() if ymd in dates}
    base = _midnight(day, tz)
    out = []
    for tid, sid, line, start_s, calls in schedule["trips"]:
        if sid in active:
            stops = tuple(Stop(c, base + a, base + d) for c, a, d in calls)
            out.append((Trip(tid, line, stops, live=False), base + start_s))
    return out


# ---- merge -------------------------------------------------------------------

def _overlay(trip: Trip, live: LiveTrip) -> Trip:
    listed = {code: (arr, dep) for code, arr, dep in live.stops}
    stops, delay = [], None
    for s in trip.stops:
        if s.code in live.skipped or s.code not in listed:
            continue   # skipped, or already passed
        arr, dep = listed[s.code]
        if arr is not None:
            delay = arr - s.arrive
        elif delay is None:
            continue   # no data and nothing earlier to go by
        else:
            arr, dep = s.arrive + delay, s.depart + delay
        stops.append(Stop(s.code, arr, dep if dep is not None else arr))
    return Trip(trip.id, trip.line, tuple(stops), live=True)


def _live_only(live: LiveTrip) -> Trip:
    stops = tuple(Stop(c, a, d) for c, a, d in live.stops if a is not None)
    return Trip(live.id, live.line, stops, live=True)


def merge_trips(scheduled: list[tuple[Trip, float]], updates: TripUpdates | None, now: float) -> list[Trip]:
    """Timetable overlaid with live predictions. `updates` None: timetable only."""
    if updates is None:
        return [t for t, _ in scheduled]
    out, seen = [], set()
    for trip, start in scheduled:
        live = updates.trips.get(trip.id)
        seen.add(trip.id)
        if live is None:
            if start > now + LIVE_HORIZON_S:
                out.append(trip)   # beyond the live horizon: timetable it is
            continue
        if not live.gone:
            out.append(_overlay(trip, live))
    for tid, live in updates.trips.items():   # added trips, or no timetable loaded
        if tid not in seen and not live.gone:
            out.append(_live_only(live))
    return out


class FixtureSchedule:
    """A recorded day's timetable (tools/record_fixtures.py --commute), replayed
    as today's so fixtures mode has a commute panel on any weekday."""

    def __init__(self, path: Path, tz: ZoneInfo) -> None:
        self._path, self._tz = Path(path), tz

    async def load(self) -> dict:
        schedule = json.loads(self._path.read_text(encoding="utf-8"))
        today = datetime.now(self._tz).strftime("%Y%m%d")
        schedule["services"] = {sid: [today] for sid in schedule["services"]}
        return schedule

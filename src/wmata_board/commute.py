"""The Children's National commute panel: every way through, not one pick. Pure.

Morning (weekdays, wall + phone): each Orange/Silver train from home, the
first Red train at Metro Center she can make after the platform-to-platform
walk, Brookland arrival, and the first shuttle slot she can walk to. The
phone can also show the same trip ending at the other station (Takoma).
Evening (phone): home again from either the hospital (shuttle -> Brookland ->
Red) or the other evening start (Takoma: Red), transferring at Metro Center.

Times on screen are floored to the minute, and waits/spare are differences of
those shown minutes, so every row adds up as she reads it. Whether a
connection is makeable is decided on the seconds. "Spare" is shuttle minus
Brookland arrival; the walk to the stop is not subtracted.

The row she said "I'm on this one" for (ride.py) is pinned to the top of its
list until the ride ends, after its trains have left. The live feed forgets a
trip's passed stops, so RideMemory keeps the last times seen for the ride's
trips; the timetable is the fallback after a restart.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from .config import CommuteConfig
from .incidents import alerts_for
from .state import FeedState
from .trips import Stop, Trip, TripUpdates, merge_trips, scheduled_trips

AM, PM = "am", "pm"
LIVE_STALE_AFTER_S = 120.0
INCIDENTS_EXPIRE_AFTER_S = 900.0   # as on the board: an incident feed this old is dropped
EARLIER_SLOTS = 2          # morning rows start two shuttles before the first target
NOTICE_UNAVAILABLE = "Commute times unavailable"


@dataclass(frozen=True, slots=True)
class Leg:
    trip: str
    line: str
    origin: str
    dest: str
    depart: float
    arrive: float
    live: bool

    def as_json(self) -> dict:
        """What the phone needs to fetch and trim this leg's trip card."""
        return {"trip": self.trip, "line": self.line, "from": self.origin, "to": self.dest}


def departures(trips: Iterable[Trip], a: str, b: str, after: float) -> list[Leg]:
    """Rides from a to b leaving at or after `after`, earliest first."""
    legs = []
    for t in trips:
        dep = None
        for s in t.stops:
            if dep is None:
                if s.code == a:
                    if s.depart < after:
                        break
                    dep = s.depart
            elif s.code == b:
                legs.append(Leg(t.id, t.line, a, b, dep, s.arrive, t.live))
                break
    return sorted(legs, key=lambda x: (x.depart, x.arrive))


def _first(legs: list[Leg], ready: float) -> Leg | None:
    return next((x for x in legs if x.depart >= ready), None)


def _local_midnight(t: float, tz: ZoneInfo) -> float:
    return datetime.combine(datetime.fromtimestamp(t, tz).date(), dtime(0, 0), tz).timestamp()


def next_slot(t: float, every_min: int, tz: ZoneInfo) -> float:
    """The first shuttle at or after t; it leaves on :00, :06, :12 ... local."""
    base = _local_midnight(t, tz)
    step = every_min * 60
    return base + math.ceil((t - base) / step - 1e-9) * step


def _min(t: float) -> int:
    return int(t // 60)


def clock(t: float, tz: ZoneInfo) -> str:
    d = datetime.fromtimestamp(t, tz)
    return f"{d.hour % 12 or 12}:{d.minute:02d}"


def _of_day(t: float, tz: ZoneInfo) -> int:
    d = datetime.fromtimestamp(t, tz)
    return d.hour * 60 + d.minute


def commute_mode(cfg: CommuteConfig, now_local: datetime) -> str | None:
    if now_local.weekday() >= 5:
        return None
    m = now_local.hour * 60 + now_local.minute
    if cfg.morning[0] <= m < cfg.morning[1]:
        return AM
    if cfg.evening[0] <= m < cfg.evening[1]:
        return PM
    return None


def _am_shuttle(second: Leg, cfg: CommuteConfig, tz: ZoneInfo) -> float:
    return next_slot(second.arrive + cfg.shuttle_walk * 60, cfg.shuttle_every, tz)


def _am_row(first: Leg, second: Leg, cfg: CommuteConfig, tz: ZoneInfo) -> dict:
    shuttle = _am_shuttle(second, cfg, tz)
    return {
        "line": first.line, "leave": clock(first.depart, tz),
        "mc_arrive": clock(first.arrive, tz), "red_leave": clock(second.depart, tz),
        "mc_wait": _min(second.depart) - _min(first.arrive),
        "brookland": clock(second.arrive, tz), "shuttle": clock(shuttle, tz),
        "spare": _min(shuttle) - _min(second.arrive),
        "target": _of_day(shuttle, tz) in cfg.shuttles,
        "live": first.live and second.live, "legs": [first.as_json(), second.as_json()],
    }


def plan_morning(trips: list[Trip], cfg: CommuteConfig, now: float, tz: ZoneInfo) -> list[dict]:
    orsv, red = cfg.transfer
    reds = departures(trips, red, cfg.shuttle_stop, now)
    earliest = min(cfg.shuttles) - EARLIER_SLOTS * cfg.shuttle_every if cfg.shuttles else None
    rows = []
    for first in departures(trips, cfg.home, orsv, now):
        second = _first(reds, first.arrive + cfg.transfer_walk * 60)
        if second is None:
            break
        if earliest is not None and _of_day(_am_shuttle(second, cfg, tz), tz) < earliest:
            continue
        rows.append(_am_row(first, second, cfg, tz))
        if len(rows) == cfg.rows:
            break
    return rows


def plan_to_station(trips: list[Trip], cfg: CommuteConfig, now: float, tz: ZoneInfo) -> list[dict]:
    """Morning to the other station (Takoma): home -> Metro Center -> Red."""
    orsv, red = cfg.transfer
    reds = departures(trips, red, cfg.evening_from, now)
    rows = []
    for first in departures(trips, cfg.home, orsv, now):
        second = _first(reds, first.arrive + cfg.transfer_walk * 60)
        if second is None:
            break
        rows.append(_to_station_row(first, second, tz))
        if len(rows) == cfg.rows:
            break
    return rows


def _to_station_row(first: Leg, second: Leg, tz: ZoneInfo) -> dict:
    return {"line": first.line, "leave": clock(first.depart, tz),
            "mc_arrive": clock(first.arrive, tz), "red_leave": clock(second.depart, tz),
            "mc_wait": _min(second.depart) - _min(first.arrive), "arrive": clock(second.arrive, tz),
            "live": first.live and second.live, "legs": [first.as_json(), second.as_json()]}


def _home_from(trips: list[Trip], cfg: CommuteConfig, origin: str, now: float) -> tuple[list[Leg], list[Leg]]:
    orsv, red = cfg.transfer
    return departures(trips, origin, red, now), departures(trips, orsv, cfg.home, now)


def _home_row(first: Leg, second: Leg, tz: ZoneInfo) -> dict:
    return {"red_leave": clock(first.depart, tz), "mc_arrive": clock(first.arrive, tz),
            "line": second.line, "mc_wait": _min(second.depart) - _min(first.arrive),
            "home": clock(second.arrive, tz), "live": first.live and second.live,
            "legs": [first.as_json(), second.as_json()]}


def plan_from_hospital(trips: list[Trip], cfg: CommuteConfig, now: float, tz: ZoneInfo) -> list[dict]:
    reds, homes = _home_from(trips, cfg, cfg.shuttle_stop, now)
    shuttle = next_slot(now, cfg.shuttle_every, tz)
    rows = []
    for _ in range(cfg.rows):
        at_stop = shuttle + cfg.shuttle_ride * 60
        first = _first(reds, at_stop + cfg.shuttle_walk * 60)
        second = first and _first(homes, first.arrive + cfg.transfer_walk * 60)
        if not second:
            break
        rows.append(_hospital_row(shuttle, first, second, cfg, tz))
        shuttle += cfg.shuttle_every * 60
    return rows


def _hospital_row(shuttle: float, first: Leg, second: Leg, cfg: CommuteConfig, tz: ZoneInfo) -> dict:
    return {"shuttle": clock(shuttle, tz), "brookland": clock(shuttle + cfg.shuttle_ride * 60, tz),
            **_home_row(first, second, tz)}


def plan_from_station(trips: list[Trip], cfg: CommuteConfig, now: float, tz: ZoneInfo) -> list[dict]:
    reds, homes = _home_from(trips, cfg, cfg.evening_from, now)
    rows = []
    for first in reds:
        second = _first(homes, first.arrive + cfg.transfer_walk * 60)
        if second is None:
            break
        rows.append(_home_row(first, second, tz))
        if len(rows) == cfg.rows:
            break
    return rows


# ---- the ride she's on -------------------------------------------------------

@dataclass
class RideMemory:
    """The last times seen for the ride's trips, and its rows as last planned.
    Owned by the app; build_commute updates it (its one mutable input)."""
    ride: tuple[str, ...] = ()
    trips: dict[str, Trip] = field(default_factory=dict)
    rows: dict[str, dict] = field(default_factory=dict)

    def track(self, ride: tuple[str, ...], trips: Iterable[Trip]) -> None:
        """Live times only (the timetable is always there to fall back on). The
        newest win; a stop the feed no longer lists (passed) is kept."""
        if ride != self.ride:
            self.ride, self.trips, self.rows = ride, {}, {}
        for t in trips:
            if t.id not in ride or not t.live:
                continue
            old = self.trips.get(t.id)
            if old is not None:
                new = {s.code: s for s in t.stops}
                kept = {s.code for s in old.stops}
                t = Trip(t.id, t.line, tuple(new.get(s.code, s) for s in old.stops) +
                         tuple(s for s in t.stops if s.code not in kept), t.live, t.headsign or old.headsign)
            self.trips[t.id] = t


def _leg_of(sources: list[Mapping[str, Trip]], trip_id: str, a: str, b: str) -> Leg | None:
    """trip_id's ride from a to b, each stop's time from the first source that
    still has it (live now, live earlier, then the timetable)."""
    def find(code: str) -> tuple[Trip, Stop] | None:
        for src in sources:
            t = src.get(trip_id)
            s = next((s for s in t.stops if s.code == code), None) if t else None
            if s is not None:
                return t, s
        return None

    start, end = find(a), find(b)
    if start is None or end is None or end[1].arrive <= start[1].depart:
        return None
    return Leg(trip_id, end[0].line, a, b, start[1].depart, end[1].arrive, start[0].live and end[0].live)


def _prev_slot(t: float, every_min: int, tz: ZoneInfo) -> float:
    """The last shuttle at or before t."""
    base = _local_midnight(t, tz)
    step = every_min * 60
    return base + math.floor((t - base) / step + 1e-9) * step


def ride_rows(ride: tuple[str, ...], sources: list[Mapping[str, Trip]], cfg: CommuteConfig,
              tz: ZoneInfo) -> dict[str, dict]:
    """The ride's row for each list it fits, by kind: "am" (hospital),
    "am-station", "pm" (hospital), "pm-station". A one-train ride (a train
    tapped on the map) fits none."""
    if len(ride) != 2:
        return {}
    orsv, red = cfg.transfer
    t1, t2 = ride
    out = {}
    first = _leg_of(sources, t1, cfg.home, orsv)
    if first is not None:
        if (second := _leg_of(sources, t2, red, cfg.shuttle_stop)) is not None:
            out["am"] = _am_row(first, second, cfg, tz)
        if (second := _leg_of(sources, t2, red, cfg.evening_from)) is not None:
            out["am-station"] = _to_station_row(first, second, tz)
    second = _leg_of(sources, t2, orsv, cfg.home)
    if second is not None:
        if (first := _leg_of(sources, t1, cfg.shuttle_stop, red)) is not None:
            shuttle = _prev_slot(first.depart - (cfg.shuttle_ride + cfg.shuttle_walk) * 60, cfg.shuttle_every, tz)
            out["pm"] = _hospital_row(shuttle, first, second, cfg, tz)
        if (first := _leg_of(sources, t1, cfg.evening_from, red)) is not None:
            out["pm-station"] = _home_row(first, second, tz)
    return out


def _trips_of(row: dict) -> tuple[str, ...]:
    return tuple(leg["trip"] for leg in row["legs"])


def _pin(rows: list[dict], kind: str, ride: tuple[str, ...], built: dict[str, dict],
         memory: RideMemory, limit: int) -> list[dict]:
    """Her row first, marked riding: as planned while it is still listed, else
    rebuilt from its trains (keeping the shuttle she was planned onto)."""
    row = next((r for r in rows if _trips_of(r) == ride), None)
    if row is not None:
        memory.rows[kind] = row
    elif kind in built:
        row = built[kind]
        if kind == "pm" and kind in memory.rows:
            planned = memory.rows[kind]
            row = {**row, "shuttle": planned["shuttle"], "brookland": planned["brookland"]}
    else:
        return rows
    return ([{**row, "riding": True}] + [r for r in rows if _trips_of(r) != ride])[:limit]


def live_updates(state: FeedState, now_mono: float, wall_now: float) -> TripUpdates | None:
    """The live trip updates if they are fresh enough to plan on, else None."""
    upd: TripUpdates | None = state.value
    age = state.age(now_mono)
    if upd is None or age is None or age > LIVE_STALE_AFTER_S:
        return None
    if upd.feed_timestamp and wall_now - upd.feed_timestamp > LIVE_STALE_AFTER_S:
        return None
    return upd


def commute_alerts(cfg: CommuteConfig, incidents: FeedState | None, now_mono: float) -> list[dict]:
    """Alerts on any line of the trip -- Red too, which the Court House board
    doesn't show. The pages merge these with the board's by id."""
    if incidents is None or incidents.value is None:
        return []
    age = incidents.age(now_mono)
    if age is not None and age > INCIDENTS_EXPIRE_AFTER_S:
        return []
    return [a.as_json() for a in alerts_for(incidents.value, cfg.lines)]


def build_commute(cfg: CommuteConfig, *, schedule: FeedState, updates: FeedState, tz: ZoneInfo,
                  now: float, now_mono: float, wall_now: float, mode: str | None = None,
                  incidents: FeedState | None = None, ride: tuple[str, ...] | None = None,
                  memory: RideMemory | None = None) -> dict:
    """`now` is the planning time (epoch); `wall_now` the real time, which differs
    only when a debug `at=` is given. `mode` overrides the time-of-day window.
    `ride`: the trips she's on. Their row is pinned to the top, and keeps the
    panel up past the end of its window."""
    now_local = datetime.fromtimestamp(now, tz)
    mode = mode or commute_mode(cfg, now_local)
    body = {"mode": mode, "name": cfg.name, "wall_platform": cfg.wall_platform,
            "live": False, "notice": None}
    if mode is None and not ride:
        return body
    live = live_updates(updates, now_mono, wall_now)
    sched = scheduled_trips(schedule.value, now_local.date(), tz) if schedule.value else []
    trips = merge_trips(sched, live, now) if sched or live is not None else []
    built: dict[str, dict] = {}
    if ride:
        memory = memory if memory is not None else RideMemory()
        memory.track(ride, trips)
        sources = [{t.id: t for t in trips if t.live}, memory.trips, {t.id: t for t in trips},
                   {t.id: t for t, _ in sched}]
        built = ride_rows(ride, sources, cfg, tz)
        if mode is None:
            mode = AM if any(k.startswith(AM) for k in built) else PM if built else None
            body["mode"] = mode
            if mode is None:
                return body
    body["alerts"] = commute_alerts(cfg, incidents, now_mono)
    if not trips and not built:
        body["notice"] = NOTICE_UNAVAILABLE
        return body
    body["live"] = live is not None
    station_name = (schedule.value or {}).get("names", {}).get(cfg.evening_from, cfg.evening_from)

    def pin(rows: list[dict], kind: str) -> list[dict]:
        return _pin(rows, kind, ride, built, memory, cfg.rows) if ride else rows

    if mode == AM:
        body["am"] = {"shuttles": [f"{m // 60 % 12 or 12}:{m % 60:02d}" for m in cfg.shuttles],
                      "rows": pin(plan_morning(trips, cfg, now, tz), "am"),
                      "station": pin(plan_to_station(trips, cfg, now, tz), "am-station"),
                      "station_name": station_name}
    else:
        body["pm"] = {"hospital": pin(plan_from_hospital(trips, cfg, now, tz), "pm"),
                      "station": pin(plan_from_station(trips, cfg, now, tz), "pm-station"),
                      "station_name": station_name}
    return body

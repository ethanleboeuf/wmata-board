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
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from .config import CommuteConfig
from .incidents import alerts_for
from .state import FeedState
from .trips import Trip, TripUpdates, merge_trips, scheduled_trips

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


def plan_morning(trips: list[Trip], cfg: CommuteConfig, now: float, tz: ZoneInfo) -> list[dict]:
    orsv, red = cfg.transfer
    reds = departures(trips, red, cfg.shuttle_stop, now)
    earliest = min(cfg.shuttles) - EARLIER_SLOTS * cfg.shuttle_every if cfg.shuttles else None
    rows = []
    for first in departures(trips, cfg.home, orsv, now):
        second = _first(reds, first.arrive + cfg.transfer_walk * 60)
        if second is None:
            break
        shuttle = next_slot(second.arrive + cfg.shuttle_walk * 60, cfg.shuttle_every, tz)
        slot = _of_day(shuttle, tz)
        if earliest is not None and slot < earliest:
            continue
        rows.append({
            "line": first.line, "leave": clock(first.depart, tz),
            "mc_arrive": clock(first.arrive, tz), "red_leave": clock(second.depart, tz),
            "mc_wait": _min(second.depart) - _min(first.arrive),
            "brookland": clock(second.arrive, tz), "shuttle": clock(shuttle, tz),
            "spare": _min(shuttle) - _min(second.arrive),
            "target": slot in cfg.shuttles, "late": bool(cfg.shuttles) and slot > max(cfg.shuttles),
            "live": first.live and second.live, "legs": [first.as_json(), second.as_json()],
        })
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
        rows.append({"line": first.line, "leave": clock(first.depart, tz),
                     "mc_arrive": clock(first.arrive, tz), "red_leave": clock(second.depart, tz),
                     "mc_wait": _min(second.depart) - _min(first.arrive), "arrive": clock(second.arrive, tz),
                     "live": first.live and second.live, "legs": [first.as_json(), second.as_json()]})
        if len(rows) == cfg.rows:
            break
    return rows


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
        rows.append({"shuttle": clock(shuttle, tz), "brookland": clock(at_stop, tz),
                     **_home_row(first, second, tz)})
        shuttle += cfg.shuttle_every * 60
    return rows


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
                  incidents: FeedState | None = None) -> dict:
    """`now` is the planning time (epoch); `wall_now` the real time, which differs
    only when a debug `at=` is given. `mode` overrides the time-of-day window."""
    now_local = datetime.fromtimestamp(now, tz)
    mode = mode or commute_mode(cfg, now_local)
    body = {"mode": mode, "name": cfg.name, "wall_platform": cfg.wall_platform,
            "live": False, "notice": None}
    if mode is None:
        return body
    body["alerts"] = commute_alerts(cfg, incidents, now_mono)
    live = live_updates(updates, now_mono, wall_now)
    sched = scheduled_trips(schedule.value, now_local.date(), tz) if schedule.value else []
    if not sched and live is None:
        body["notice"] = NOTICE_UNAVAILABLE
        return body
    trips = merge_trips(sched, live, now)
    body["live"] = live is not None
    station_name = (schedule.value or {}).get("names", {}).get(cfg.evening_from, cfg.evening_from)
    if mode == AM:
        body["am"] = {"shuttles": [f"{m // 60 % 12 or 12}:{m % 60:02d}" for m in cfg.shuttles],
                      "rows": plan_morning(trips, cfg, now, tz),
                      "station": plan_to_station(trips, cfg, now, tz), "station_name": station_name}
    else:
        body["pm"] = {"hospital": plan_from_hospital(trips, cfg, now, tz),
                      "station": plan_from_station(trips, cfg, now, tz),
                      "station_name": station_name}
    return body

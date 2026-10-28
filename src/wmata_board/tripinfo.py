"""One train's details for the phone's tap card (/api/trip/{id}). Pure.

Live predictions list every remaining stop; a trip beyond the live horizon
falls back to the timetable, which only holds the commute stations (good
enough to show a commute leg). WMATA's trip updates carry no delay field, so
lateness is the live time minus the timetable time at the first remaining
stop both know -- a commute station -- and is omitted when there is none.
Her commute stations (`mine`) are marked, so the card can always show them,
and where she'd get off right now (`off`), so a map train's ride can end there.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from zoneinfo import ZoneInfo

from .commute import clock
from .positions import PositionsSnapshot
from .trips import Trip, TripUpdates

PASSED_GRACE_S = 30.0   # a stop this far in the past still shows (the train may be at it)


def station_names(network: Mapping | None, schedule: Mapping | None) -> dict[str, str]:
    names = dict((schedule or {}).get("names", {}))
    for st in (network or {}).get("stations", []):
        for code in st["codes"]:
            names[code] = st["name"]
    return names


def _cars(positions: PositionsSnapshot | None, trip_id: str) -> int | None:
    if positions is None:
        return None
    return next((v.cars for v in positions.vehicles if v.trip_id == trip_id), None)


def trip_detail(trip_id: str, *, live: TripUpdates | None, scheduled: list[Trip],
                names: Mapping[str, str], positions: PositionsSnapshot | None,
                now: float, tz: ZoneInfo, mine: Collection[str] = (),
                off: Collection[str] = ()) -> dict | None:
    """None when neither source knows the trip (or it was cancelled)."""
    sched = next((t for t in scheduled if t.id == trip_id), None)
    lt = live.trips.get(trip_id) if live else None
    if lt is not None and lt.gone:
        return None
    if lt is not None:
        line, is_live = lt.line, True
        stops = [(code, arr or dep) for code, arr, dep in lt.stops]
        terminal = lt.stops[-1][0] if lt.stops else None
        destination = names.get(terminal, "") if terminal else ""
        delay = None
        if sched is not None:
            planned = {s.code: s.arrive for s in sched.stops}
            delay = next((round(t - planned[c]) for c, t in stops if t is not None and c in planned), None)
    elif sched is not None:
        line, is_live, delay = sched.line, False, None
        stops = [(s.code, s.arrive) for s in sched.stops]
        destination = names.get(sched.stops[-1].code, "") if sched.stops else ""
    else:
        return None
    if sched is not None and sched.headsign:   # the timetable's headsign beats our last stop
        destination = sched.headsign
    upcoming = [(c, t) for c, t in stops if t is None or t >= now - PASSED_GRACE_S]
    return {
        "id": trip_id, "line": line, "destination": destination,
        "cars": _cars(positions, trip_id), "delay_s": delay, "live": is_live,
        "stops": [{"code": c, "name": names.get(c, c), "time": clock(t, tz) if t is not None else None,
                   "t": round(t) if t is not None else None, "mine": c in mine, "off": c in off}
                  for c, t in upcoming],
    }

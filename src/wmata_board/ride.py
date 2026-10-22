"""The easter egg: the one trip she said "I'm on this one" for. Pure, plus a
tiny JSON file so a restart keeps it.

A ride is up to two trips (a commute row: the first until `switch_at`, then
the second) and ends at `until`. The phone sets it; every map (wall and
phones) gets the trip to draw the rider on in /api/positions.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_RIDE_S = 4 * 3600          # a ride ending further out than this is refused
_TRIP_RE = re.compile(r"^[\w.:-]{1,64}$")


@dataclass(frozen=True, slots=True)
class Ride:
    trips: tuple[str, ...]
    switch_at: float | None    # epoch s; None: one train
    until: float               # epoch s

    def as_json(self) -> dict:
        return {**asdict(self), "trips": list(self.trips)}


def parse_ride(body: object, now: float) -> Ride:
    """A ride from the phone's JSON; ValueError says what's wrong."""
    if not isinstance(body, dict):
        raise ValueError("expected an object")
    trips, switch_at, until = body.get("trips"), body.get("switch_at"), body.get("until")
    if (not isinstance(trips, list) or not 1 <= len(trips) <= 2
            or not all(isinstance(t, str) and _TRIP_RE.match(t) for t in trips)):
        raise ValueError("trips: one or two trip ids")
    if isinstance(until, bool) or not isinstance(until, (int, float)) or not now < until <= now + MAX_RIDE_S:
        raise ValueError("until: an epoch time within 4 h")
    if switch_at is not None and (isinstance(switch_at, bool) or not isinstance(switch_at, (int, float))):
        raise ValueError("switch_at: an epoch time or null")
    return Ride(tuple(trips), None if len(trips) == 1 or switch_at is None else float(switch_at), float(until))


def ride_trip(ride: Ride | None, now: float) -> str | None:
    """The trip the rider is on right now."""
    if ride is None or now >= ride.until:
        return None
    if len(ride.trips) > 1 and ride.switch_at is not None and now >= ride.switch_at:
        return ride.trips[1]
    return ride.trips[0]


def load_ride(path: Path) -> Ride | None:
    try:
        ride = json.loads(path.read_text(encoding="utf-8"))
        return Ride(tuple(ride["trips"]), ride["switch_at"], ride["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_ride(path: Path, ride: Ride | None) -> None:
    try:
        if ride is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ride.as_json()), encoding="utf-8")
    except OSError:
        pass   # the ride still works until a restart

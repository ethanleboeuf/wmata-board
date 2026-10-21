"""GTFS-RT rail vehicle positions -> the trains the map draws. Pure.

`vehicle.license_plate` is "<cars>_<car numbers>" (e.g. "8_7202-7203...").
Only revenue trains on one of the six lines are kept. `trip_id` links a train
to its live stop predictions (trips.py) for the phone's tap-for-details card.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .lines import ROUTE_LINES
from .wmata import WmataError

POSITIONS_STALE_AFTER_S = 120.0


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: str
    line: str
    lat: float
    lon: float
    heading: float | None
    cars: int | None
    trip_id: str | None = None

    def as_json(self) -> dict:
        return {"id": self.id, "line": self.line, "lat": self.lat, "lon": self.lon,
                "heading": self.heading, "cars": self.cars, "trip_id": self.trip_id}


@dataclass(frozen=True, slots=True)
class PositionsSnapshot:
    feed_timestamp: int
    vehicles: tuple[Vehicle, ...]


def cars_from_plate(plate: str) -> int | None:
    head = (plate or "").split("_", 1)[0]
    return int(head) if head.isdigit() else None


def decode_positions(data: bytes) -> PositionsSnapshot:
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(data)
    except DecodeError:
        raise WmataError("parse", "bad GTFS-RT vehicle positions") from None
    vehicles = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        line = ROUTE_LINES.get(v.trip.route_id)
        if line is None or not v.HasField("position"):
            continue
        pos = v.position
        vehicles.append(Vehicle(
            id=v.vehicle.id or entity.id, line=line,
            lat=round(pos.latitude, 6), lon=round(pos.longitude, 6),
            heading=round(pos.bearing, 1) if pos.HasField("bearing") else None,
            cars=cars_from_plate(v.vehicle.license_plate),
            trip_id=v.trip.trip_id or None,
        ))
    return PositionsSnapshot(int(feed.header.timestamp), tuple(vehicles))

"""Track geometry and stations from WMATA's rail GTFS static zip.

Per line: the longest shape (by shape_dist_traveled), oriented W->E (S->N
for Green/Yellow) so lines sharing track run the same way and their lane
offsets land on consistent sides, simplified to ~2 m.

Transfer stations: a combined stop_id (STN_A01_C01) or three or more
neighbouring stations across all lines (Rosslyn, Pentagon, East Falls
Church, King St, Stadium-Armory ...). Court House, with two neighbours, is not.

`python -m wmata_board.network rail.zip out.json` writes the fixture.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import os
import sys
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path

from .lines import NORTH_SOUTH, ROUTE_LINES
from .wmata import WmataError

log = logging.getLogger("wmata_board.network")
SIMPLIFY_EPS_DEG = 0.00002
MAX_AGE_S = 86400.0


def _rows(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))


def simplify(points: list, eps: float) -> list:
    """Douglas-Peucker, iterative (shapes run to thousands of points)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x0, y0), (x1, y1) = points[a], points[b]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1e-12
        best, best_d = None, eps
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / length
            if d > best_d:
                best, best_d = i, d
        if best is not None:
            keep[best] = True
            stack += [(a, best), (best, b)]
    return [p for p, k in zip(points, keep) if k]


def _orient(line: str, seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
    axis = 1 if line in NORTH_SOUTH else 0       # (lon, lat): compare lat for N-S lines
    return seq[::-1] if seq[0][axis] > seq[-1][axis] else seq


def build_network(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        route_line = {r["route_id"]: ROUTE_LINES[r["route_id"]]
                      for r in _rows(z, "routes.txt") if r["route_id"] in ROUTE_LINES}
        shapes_by_line: dict[str, set[str]] = defaultdict(set)
        trip_of_shape: dict[str, str] = {}
        for t in _rows(z, "trips.txt"):
            line = route_line.get(t["route_id"])
            if line:
                shapes_by_line[line].add(t["shape_id"])
                trip_of_shape.setdefault(t["shape_id"], t["trip_id"])

        wanted_shapes = set().union(*shapes_by_line.values()) if shapes_by_line else set()
        points: dict[str, list[tuple[int, float, float, float]]] = defaultdict(list)
        for r in _rows(z, "shapes.txt"):
            if r["shape_id"] in wanted_shapes:
                points[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lat"]),
                                              float(r["shape_pt_lon"]), float(r["shape_dist_traveled"] or 0)))

        lines = {}
        for line, sids in shapes_by_line.items():
            candidates = [s for s in sids if points.get(s)]
            if not candidates:
                continue
            best = max(candidates, key=lambda s: (max(p[3] for p in points[s]), len(points[s])))
            seq = [(lon, lat) for _, lat, lon, _ in sorted(points[best])]
            lines[line] = [[round(x, 6), round(y, 6)] for x, y in simplify(_orient(line, seq), SIMPLIFY_EPS_DEG)]

        stops = list(_rows(z, "stops.txt"))
        parent = {s["stop_id"]: s.get("parent_station", "") for s in stops}

        def station_of(stop_id: str) -> str:
            for _ in range(5):
                up = parent.get(stop_id, "")
                if not up:
                    break
                stop_id = up
            return stop_id

        trips = set(trip_of_shape.values())
        sequences: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for r in _rows(z, "stop_times.txt"):
            if r["trip_id"] in trips:
                sequences[r["trip_id"]].append((int(r["stop_sequence"]), station_of(r["stop_id"])))
        neighbours: dict[str, set[str]] = defaultdict(set)
        for seq in sequences.values():
            ordered = [s for _, s in sorted(seq)]
            for a, b in zip(ordered, ordered[1:]):
                if a != b:
                    neighbours[a].add(b)
                    neighbours[b].add(a)

        stations = []
        for s in stops:
            if s.get("location_type") != "1" or not s["stop_id"].startswith("STN_"):
                continue
            codes = s["stop_id"][4:].split("_")
            stations.append({"codes": codes, "name": s["stop_name"],
                             "lon": round(float(s["stop_lon"]), 6), "lat": round(float(s["stop_lat"]), 6),
                             "transfer": len(codes) > 1 or len(neighbours[s["stop_id"]]) >= 3})
    return {"lines": lines, "stations": stations}


class NetworkCache:
    """data/network.json, rebuilt from the GTFS static zip once a day. A stale
    cache is served if the download fails -- track geometry barely changes.

    `build` turns the zip into what is cached (the commute timetable reuses
    this with trips.build_schedule); `key` names what it was built for, and a
    cache built for another key is ignored."""

    def __init__(self, client, path: Path, *, max_age_s: float = MAX_AGE_S,
                 clock: Callable[[], float] = time.time,
                 build: Callable[[bytes], dict] = build_network, key: str = "") -> None:
        self._client, self._path, self._max_age, self._clock = client, Path(path), max_age_s, clock
        self._build, self._key = build, key
        self._memo: dict | None = None
        self._built_at: float | None = None

    def _read(self) -> tuple[dict, float] | None:
        try:
            blob = json.loads(self._path.read_text(encoding="utf-8"))
            if blob.get("key", "") != self._key:
                return None
            return blob["network"], float(blob["built_at"])
        except (FileNotFoundError, ValueError, KeyError, TypeError, AttributeError):
            return None

    async def load(self) -> dict:
        if self._memo is None and (cached := self._read()):
            self._memo, self._built_at = cached
        if self._memo is not None and self._clock() - self._built_at < self._max_age:
            return self._memo
        try:
            data = await self._client.gtfs_static()
            built = await asyncio.to_thread(self._build, data)
        except (WmataError, zipfile.BadZipFile, KeyError, ValueError) as exc:
            if self._memo is not None:
                log.warning("%s refresh failed (%s); keeping cached copy", self._path.name, exc)
                return self._memo
            if isinstance(exc, WmataError):
                raise
            raise WmataError("parse", f"bad GTFS static zip: {exc}") from None
        self._memo, self._built_at = built, self._clock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"built_at": self._built_at, "key": self._key, "network": built}), encoding="utf-8")
        os.replace(tmp, self._path)
        log.info("%s rebuilt", self._path.name)
        return built


class FixtureNetwork:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def load(self) -> dict:
        return json.loads(self._path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.write_text(json.dumps(build_network(src.read_bytes()), separators=(",", ":")), encoding="utf-8")
    print("wrote", out)

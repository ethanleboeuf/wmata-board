"""A stand-in for WmataClient that replays recorded responses (`--fixtures`).

Lets the whole board run on a laptop with no key and no network. Position
snapshots are replayed in order, one per call, wrapping at the end -- they
were recorded 5 s apart, the same as the positions cadence.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from google.transit import gtfs_realtime_pb2

from .wmata import WmataError


class FixtureClient:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._snapshots = sorted((self._root / "positions").glob("*.pb"))
        self._next = 0

    def _load(self, name: str) -> Any:
        try:
            return json.loads((self._root / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise WmataError("http", f"fixture {name} missing") from None

    async def predictions(self, stations: Sequence[str]) -> Any:
        return self._load(f"predictions_{','.join(stations)}.json")

    async def incidents(self) -> Any:
        return self._load("incidents.json")

    async def station_info(self, code: str) -> Any:
        return self._load(f"station_info_{code}.json")

    async def station_times(self, code: str) -> Any:
        return self._load(f"station_times_{code}.json")

    async def vehicle_positions(self) -> bytes:
        if not self._snapshots:
            raise WmataError("http", "no position fixtures")
        data = self._snapshots[self._next % len(self._snapshots)].read_bytes()
        self._next += 1
        # The recordings are old; stamp them 'now' so the map isn't flagged stale.
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(data)
        feed.header.timestamp = int(time.time())
        return feed.SerializeToString()

    async def gtfs_static(self) -> bytes:
        raise WmataError("http", "fixtures mode has no GTFS static zip (uses network.json)")

    async def aclose(self) -> None:
        pass

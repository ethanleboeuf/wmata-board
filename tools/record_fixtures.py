"""Capture live WMATA responses as test fixtures.

    set -a; . ~/wmata-board.env; set +a
    .venv/bin/python tools/record_fixtures.py tests/fixtures --station K01 --positions 12
    .venv/bin/python tools/record_fixtures.py tests/fixtures --commute 2026-10-22

Writes predictions_<code>.json, predictions_All.json (what the server polls),
incidents.json (only with --incidents, since the sample one is hand-made),
station_info_<code>.json, station_times_<code>.json
and positions/vp_<ms>.pb snapshots 5 s apart. --commute DATE writes
trip_updates.pb and schedule.json: the commute stations' timetable for that one
service day (fixtures mode replays it as "today").
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from wmata_board.config import load_config
from wmata_board.trips import build_schedule
from wmata_board.wmata import WmataClient

REPO = Path(__file__).resolve().parents[1]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--station", default="K01")
    p.add_argument("--positions", type=int, default=0, help="number of GTFS-RT snapshots to record")
    p.add_argument("--incidents", action="store_true", help="overwrite incidents.json with the live feed")
    p.add_argument("--commute", metavar="YYYY-MM-DD", help="record trip updates + that day's commute timetable")
    args = p.parse_args()

    key = os.environ.get("WMATA_API_KEY")
    if not key:
        raise SystemExit("WMATA_API_KEY is not set")
    client = WmataClient(key)
    out, code = args.out, args.station
    out.mkdir(parents=True, exist_ok=True)

    def save(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print("wrote", out / name)

    save(f"predictions_{code}.json", await client.predictions([code]))
    save("predictions_All.json", await client.predictions(["All"]))
    save(f"station_info_{code}.json", await client.station_info(code))
    save(f"station_times_{code}.json", await client.station_times(code))
    if args.incidents:
        save("incidents.json", await client.incidents())
    if args.commute:
        stations = load_config(REPO / "config.toml", environ={}).commute.stations
        (out / "trip_updates.pb").write_bytes(await client.trip_updates())
        print("wrote", out / "trip_updates.pb")
        sched = build_schedule(await client.gtfs_static(), stations)
        ymd = args.commute.replace("-", "")
        sched["services"] = {sid: [ymd] for sid, dates in sched["services"].items() if ymd in dates}
        sched["trips"] = [t for t in sched["trips"] if t[1] in sched["services"]]
        (out / "schedule.json").write_text(json.dumps(sched, separators=(",", ":")), encoding="utf-8")
        print("wrote", out / "schedule.json", len(sched["trips"]), "trips")
    if args.positions:
        (out / "positions").mkdir(exist_ok=True)
        for _ in range(args.positions):
            path = out / "positions" / f"vp_{int(time.time() * 1000)}.pb"
            path.write_bytes(await client.vehicle_positions())
            print("wrote", path)
            await asyncio.sleep(5)
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

"""Capture live WMATA responses as test fixtures.

    set -a; . ~/wmata-board.env; set +a
    .venv/bin/python tools/record_fixtures.py tests/fixtures --station K01 --positions 12

Writes predictions_<code>.json, incidents.json (only with --incidents, since
the sample one is hand-made), station_info_<code>.json, station_times_<code>.json
and positions/vp_<ms>.pb snapshots 5 s apart.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from wmata_board.wmata import WmataClient


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--station", default="K01")
    p.add_argument("--positions", type=int, default=0, help="number of GTFS-RT snapshots to record")
    p.add_argument("--incidents", action="store_true", help="overwrite incidents.json with the live feed")
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
    save(f"station_info_{code}.json", await client.station_info(code))
    save(f"station_times_{code}.json", await client.station_times(code))
    if args.incidents:
        save("incidents.json", await client.incidents())
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

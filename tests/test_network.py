import io
import json
import zipfile

import pytest

from wmata_board.network import FixtureNetwork, NetworkCache, build_network, simplify
from wmata_board.wmata import WmataError


def csv(header, *rows):
    return "\n".join([header, *(",".join(map(str, r)) for r in rows)]) + "\n"


def gtfs_zip() -> bytes:
    files = {
        "routes.txt": csv("route_id,route_short_name,route_color", ("ORANGE", "O", "ED8B00"),
                          ("BLUE", "B", "009CDE"), ("GREEN", "G", "00B140"), ("SHUTTLE", "X", "000000")),
        "trips.txt": csv("route_id,service_id,trip_id,shape_id",
                         ("ORANGE", "s", "t1", "or_long"), ("ORANGE", "s", "t2", "or_short"),
                         ("BLUE", "s", "t3", "bl"), ("GREEN", "s", "t4", "gr"), ("SHUTTLE", "s", "t5", "x")),
        # or_long runs E->W in the file; build_network must flip it to W->E
        "shapes.txt": csv("shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled",
                          ("or_long", 38.90, -77.00, 1, 0), ("or_long", 38.90, -77.05, 2, 5),
                          ("or_long", 38.90, -77.10, 3, 10),
                          ("or_short", 38.90, -77.05, 1, 0), ("or_short", 38.90, -77.10, 2, 5),
                          ("bl", 38.85, -77.05, 1, 0), ("bl", 38.90, -77.05, 2, 6),
                          # gr runs N->S in the file; must become S->N
                          ("gr", 38.95, -77.02, 1, 0), ("gr", 38.85, -77.02, 2, 11),
                          ("x", 38.0, -77.0, 1, 0), ("x", 38.1, -77.0, 2, 1)),
        "stops.txt": csv("stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station",
                         ("STN_K01", "Court House", 38.90, -77.10, 1, ""),
                         ("STN_C05", "Rosslyn", 38.90, -77.05, 1, ""),
                         ("STN_A01_C01", "Metro Center", 38.90, -77.00, 1, ""),
                         ("STN_J02", "Van Dorn", 38.85, -77.05, 1, ""),
                         ("PF_K01_1", "Court House", 38.90, -77.10, 0, "STN_K01"),
                         ("PF_C05_1", "Rosslyn", 38.90, -77.05, 0, "STN_C05"),
                         ("PF_C01_1", "Metro Center", 38.90, -77.00, 0, "STN_A01_C01"),
                         ("PF_J02_1", "Van Dorn", 38.85, -77.05, 0, "STN_J02")),
        "stop_times.txt": csv("trip_id,arrival_time,departure_time,stop_id,stop_sequence",
                              ("t1", "", "", "PF_C01_1", 1), ("t1", "", "", "PF_C05_1", 2),
                              ("t1", "", "", "PF_K01_1", 3),
                              ("t3", "", "", "PF_J02_1", 1), ("t3", "", "", "PF_C05_1", 2)),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, "﻿" + text)   # WMATA's files carry a BOM
    return buf.getvalue()


@pytest.fixture
def net():
    return build_network(gtfs_zip())


def test_longest_shape_per_line_oriented(net):
    assert set(net["lines"]) == {"OR", "BL", "GR"}
    assert net["lines"]["OR"] == [[-77.1, 38.9], [-77.0, 38.9]]      # W->E, collinear midpoint simplified away
    assert net["lines"]["GR"][0][1] < net["lines"]["GR"][-1][1]       # S->N


def test_stations_and_transfers(net):
    by = {s["name"]: s for s in net["stations"]}
    assert set(by) == {"Court House", "Rosslyn", "Metro Center", "Van Dorn"}
    assert by["Metro Center"]["codes"] == ["A01", "C01"]
    assert by["Metro Center"]["transfer"] is True     # combined id
    assert by["Rosslyn"]["transfer"] is True          # three neighbours
    assert by["Court House"]["transfer"] is False
    assert by["Van Dorn"]["transfer"] is False
    assert by["Court House"]["lon"] == -77.1


def test_simplify_keeps_corners():
    pts = [(0, 0), (1, 0.000001), (2, 0), (2, 1)]
    assert simplify(pts, 0.001) == [(0, 0), (2, 0), (2, 1)]
    assert simplify([(0, 0)], 1) == [(0, 0)]


def test_fixture_network_is_real(fixtures):
    data = json.loads((fixtures / "network.json").read_text(encoding="utf-8"))
    assert set(data["lines"]) == {"RD", "OR", "SV", "BL", "GR", "YL"}
    assert len(data["stations"]) >= 95
    transfers = {c for s in data["stations"] if s["transfer"] for c in s["codes"]}
    assert {"C05", "A01", "C01", "D03", "F03", "B06", "E06", "K05"} <= transfers
    assert not {"K01", "K02", "K04"} & transfers


class FakeClient:
    def __init__(self, data=None, fail=False):
        self.calls, self.data, self.fail = 0, data, fail

    async def gtfs_static(self):
        self.calls += 1
        if self.fail:
            raise WmataError("network", "down")
        return self.data


async def test_cache_builds_then_reuses(tmp_path):
    client = FakeClient(gtfs_zip())
    clock = [1000.0]
    cache = NetworkCache(client, tmp_path / "network.json", clock=lambda: clock[0])
    first = await cache.load()
    assert client.calls == 1 and (tmp_path / "network.json").exists()
    assert await cache.load() == first and client.calls == 1
    clock[0] += 86401
    await cache.load()
    assert client.calls == 2


async def test_cache_survives_restart_and_download_failure(tmp_path):
    path = tmp_path / "network.json"
    await NetworkCache(FakeClient(gtfs_zip()), path, clock=lambda: 0.0).load()
    stale = NetworkCache(FakeClient(fail=True), path, clock=lambda: 10 * 86400.0)
    assert (await stale.load())["lines"]          # stale cache beats nothing
    with pytest.raises(WmataError):
        await NetworkCache(FakeClient(fail=True), tmp_path / "none.json").load()


async def test_fixture_network(fixtures):
    assert "lines" in await FixtureNetwork(fixtures / "network.json").load()

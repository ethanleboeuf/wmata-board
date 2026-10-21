import io
import json
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from wmata_board.network import NetworkCache
from wmata_board.trips import (LIVE_HORIZON_S, FixtureSchedule, LiveTrip, Stop, Trip, TripUpdates,
                               build_schedule, decode_trip_updates, merge_trips, scheduled_trips,
                               station_code)
from wmata_board.wmata import WmataError

ET = ZoneInfo("America/New_York")
STATIONS = ("K01", "C01", "A01", "B05", "B07")


def at(hm: str) -> float:
    h, m, *s = (int(x) for x in hm.split(":"))
    return datetime(2026, 10, 22, h, m, s[0] if s else 0, tzinfo=ET).timestamp()


def test_station_code():
    assert station_code("PF_A01_1") == "A01"
    assert station_code("PF_C01_C") == "C01"
    assert station_code("STN_A01_C01") is None
    assert station_code("NODE_B05_MZ") is None


# ---- live --------------------------------------------------------------------

def test_decode_recorded_trip_updates(fixtures):
    upd = decode_trip_updates((fixtures / "trip_updates.pb").read_bytes(), STATIONS)
    assert upd.feed_timestamp > 1_700_000_000
    assert len(upd.trips) > 50
    lines = {t.line for t in upd.trips.values()}
    assert {"RD", "OR", "SV"} <= lines
    codes = {c for t in upd.trips.values() for c, _, _ in t.stops}
    assert codes <= set(STATIONS) and {"A01", "B05"} <= codes
    some = next(t for t in upd.trips.values() if len(t.stops) >= 2 and all(a for _, a, _ in t.stops))
    times = [a for _, a, _ in some.stops]
    assert times == sorted(times)


def test_decode_rejects_garbage():
    with pytest.raises(WmataError) as err:
        decode_trip_updates(b"\xff\xfe not protobuf", STATIONS)
    assert err.value.kind == "parse"


# ---- timetable -----------------------------------------------------------------

def gtfs_zip() -> bytes:
    files = {
        "calendar_dates.txt": "service_id,date,exception_type\nWK,20261022,1\nWK,20261023,1\nSA,20261024,1\nWK,20261026,2\n",
        "trips.txt": "route_id,service_id,trip_id,shape_id,trip_headsign\nSILVER,WK,t1,s,Largo\n"
                     "RED,WK,t2,s,Glenmont\nBUS,WK,t3,s,X\nRED,SA,t4,s,Glenmont\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "t1,07:20:00,07:20:00,PF_N06_C,1\n"          # terminal: sets start, not a commute stop
                          "t1,07:38:00,07:38:30,PF_K01_C,10\n"
                          "t1,07:49:00,07:49:30,PF_C01_C,16\n"
                          "t2,07:51:00,07:51:20,PF_A01_1,15\n"         # only one commute stop: dropped
                          "t3,07:00:00,07:00:00,PF_K01_C,1\nt3,07:10:00,07:10:00,PF_C01_C,2\n"
                          "t4,25:10:00,25:10:00,PF_A01_1,1\nt4,25:22:00,25:22:00,PF_B05_C,2\n",
        "stops.txt": "stop_id,stop_name,location_type,parent_station\n"
                     "STN_K01,Court House,1,\nSTN_A01_C01,Metro Center,1,\nSTN_B07,Takoma,1,\nPF_K01_C,Court House,0,STN_K01\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_build_schedule():
    s = build_schedule(gtfs_zip(), STATIONS)
    assert s["trips"] == [["t1", "WK", "SV", 7 * 3600 + 1200, [["K01", 27480, 27510], ["C01", 28140, 28170]], "Largo"],
                          ["t4", "SA", "RD", 25 * 3600 + 600, [["A01", 90600, 90600], ["B05", 91320, 91320]], "Glenmont"]]
    assert s["services"] == {"WK": ["20261022", "20261023"], "SA": ["20261024"]}
    assert s["names"] == {"K01": "Court House", "A01": "Metro Center", "C01": "Metro Center", "B07": "Takoma"}


def test_scheduled_trips_for_a_day():
    s = build_schedule(gtfs_zip(), STATIONS)
    [(trip, start)] = scheduled_trips(s, date(2026, 10, 22), ET)
    assert trip == Trip("t1", "SV", (Stop("K01", at("7:38"), at("7:38:30")), Stop("C01", at("7:49"), at("7:49:30"))),
                        False, headsign="Largo")
    assert start == at("7:20")
    assert scheduled_trips(s, date(2026, 10, 25), ET) == []
    # GTFS times past 24h belong to the service day they started on.
    [(late, _)] = scheduled_trips(s, date(2026, 10, 24), ET)
    assert datetime.fromtimestamp(late.stops[0].arrive, ET) == datetime(2026, 10, 25, 1, 10, tzinfo=ET)


async def test_fixture_schedule_is_replayed_as_today(fixtures):
    s = await FixtureSchedule(fixtures / "schedule.json", ET).load()
    today = datetime.now(ET).strftime("%Y%m%d")
    assert s["services"] and all(d == [today] for d in s["services"].values())
    assert len(s["trips"]) > 300
    assert s["names"]["B07"] == "Takoma"


async def test_schedule_cache_ignores_a_cache_built_for_other_stations(tmp_path):
    class Client:
        calls = 0

        async def gtfs_static(self):
            Client.calls += 1
            return gtfs_zip()

    path = tmp_path / "schedule.json"
    path.write_text(json.dumps({"built_at": 0, "key": "K01", "network": {"old": True}}), encoding="utf-8")
    cache = NetworkCache(Client(), path, key=",".join(STATIONS), clock=lambda: 1.0,
                         build=lambda data: build_schedule(data, STATIONS))
    s = await cache.load()
    assert "trips" in s and Client.calls == 1
    assert json.loads(path.read_text(encoding="utf-8"))["key"] == ",".join(STATIONS)


# ---- merge -------------------------------------------------------------------------

def sched(tid, start, *calls, line="RD"):
    return Trip(tid, line, tuple(Stop(c, at(t), at(t)) for c, t in calls), False), at(start)


def live(tid, *calls, gone=False, skipped=(), line="RD"):
    return LiveTrip(tid, line, gone, tuple((c, t and at(t), t and at(t)) for c, t in calls), frozenset(skipped))


def merged(scheduled, *lives, now="7:30"):
    return {t.id: t for t in merge_trips(scheduled, TripUpdates(int(at(now)), {x.id: x for x in lives}), at(now))}


def test_no_live_data_means_the_timetable():
    s = [sched("a", "7:00", ("A01", "7:51"), ("B05", "8:03"))]
    assert merge_trips(s, None, at("7:30")) == [s[0][0]]


def test_live_times_replace_the_timetable_and_passed_stops_drop():
    s = [sched("a", "7:00", ("K01", "7:28"), ("C01", "7:39"), ("A01", "7:41"))]
    t = merged(s, live("a", ("C01", "7:40"), ("A01", "7:42")))["a"]
    assert t.live and [(x.code, x.arrive) for x in t.stops] == [("C01", at("7:40")), ("A01", at("7:42"))]


def test_a_stop_without_a_live_time_takes_the_delay_before_it():
    s = [sched("a", "7:00", ("A01", "7:51"), ("B05", "8:03"))]
    t = merged(s, live("a", ("A01", "7:53"), ("B05", None)))["a"]
    assert [x.arrive for x in t.stops] == [at("7:53"), at("8:05")]


def test_skipped_and_cancelled():
    s = [sched("a", "7:00", ("A01", "7:51"), ("B05", "8:03")), sched("b", "7:05", ("A01", "7:56"), ("B05", "8:08"))]
    out = merged(s, live("a", ("A01", "7:51"), ("B05", "8:03"), skipped={"B05"}),
                 live("b", ("A01", "7:56"), ("B05", "8:08"), gone=True))
    assert [x.code for x in out["a"].stops] == ["A01"]
    assert "b" not in out


def test_unlisted_timetable_trips_are_dropped_inside_the_live_horizon_only():
    near = sched("near", "7:45", ("A01", "8:20"), ("B05", "8:32"))   # starts within 20 min: should be listed
    far = sched("far", "7:55", ("A01", "8:30"), ("B05", "8:42"))
    assert at("7:55") - at("7:30") > LIVE_HORIZON_S
    out = merged([near, far])
    assert set(out) == {"far"} and out["far"].live is False


def test_added_live_trips_are_kept():
    out = merged([], live("extra", ("B07", "7:40"), ("A01", "7:58"), ("B05", None)))
    assert [x.code for x in out["extra"].stops] == ["B07", "A01"]


async def test_fixture_trip_updates_are_shifted_to_now(fixtures):
    import time

    from wmata_board.fixtures import FixtureClient

    raw = decode_trip_updates((fixtures / "trip_updates.pb").read_bytes())
    now = decode_trip_updates(await FixtureClient(fixtures).trip_updates())
    shift = now.feed_timestamp - raw.feed_timestamp
    assert abs(now.feed_timestamp - time.time()) < 5
    tid, trip = next((k, t) for k, t in raw.trips.items() if t.stops and t.stops[0][1])
    assert now.trips[tid].stops[0][1] == trip.stops[0][1] + shift

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from wmata_board.commute import plan_from_hospital, plan_morning
from wmata_board.config import CommuteConfig
from wmata_board.positions import PositionsSnapshot, Vehicle
from wmata_board.tripinfo import station_names, trip_detail
from wmata_board.trips import (FixtureSchedule, LiveTrip, Stop, Trip, TripUpdates, decode_trip_updates,
                               merge_trips, scheduled_trips)

ET = ZoneInfo("America/New_York")
NAMES = {"K01": "Court House", "C01": "Metro Center", "D01": "Federal Triangle", "G05": "Largo"}


def at(hm):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 10, 22, h, m, tzinfo=ET).timestamp()


SCHED = Trip("sv1", "SV", (Stop("K01", at("7:38"), at("7:38")), Stop("C01", at("7:49"), at("7:49"))), False,
             headsign="Largo")
LIVE = LiveTrip("sv1", "SV", False, (("K01", at("7:41"), at("7:41")), ("C01", at("7:52"), at("7:52")),
                                     ("D01", None, None), ("G05", at("8:40"), at("8:40"))), frozenset())
POS = PositionsSnapshot(0, (Vehicle("v1", "SV", 38.9, -77.1, None, 6, "sv1"),))


def detail(trip_id="sv1", *, live=LIVE, scheduled=(SCHED,), now="7:30"):
    upd = TripUpdates(0, {live.id: live}) if live else None
    return trip_detail(trip_id, live=upd, scheduled=list(scheduled), names=NAMES, positions=POS, now=at(now), tz=ET)


def test_live_trip_with_delay_cars_and_remaining_stops():
    d = detail()
    assert (d["line"], d["destination"], d["cars"], d["live"], d["delay_s"]) == ("SV", "Largo", 6, True, 180)
    assert [(s["name"], s["time"]) for s in d["stops"]] == [
        ("Court House", "7:41"), ("Metro Center", "7:52"), ("Federal Triangle", None), ("Largo", "8:40")]


def test_her_stations_are_marked():
    upd = TripUpdates(0, {"sv1": LIVE})
    d = trip_detail("sv1", live=upd, scheduled=[SCHED], names=NAMES, positions=POS, now=at("7:30"), tz=ET,
                    mine={"C01", "B05"})
    assert [s["mine"] for s in d["stops"]] == [False, True, False, False]
    assert not any(s["mine"] for s in detail()["stops"])


def test_passed_stops_drop():
    assert [s["code"] for s in detail(now="7:45")["stops"]] == ["C01", "D01", "G05"]


def test_live_only_trip_names_its_last_stop_and_has_no_delay():
    d = detail(scheduled=())
    assert (d["destination"], d["delay_s"]) == ("Largo", None)


def test_timetable_fallback():
    d = detail(live=None)
    assert (d["live"], d["destination"], d["delay_s"]) == (False, "Largo", None)
    assert [s["time"] for s in d["stops"]] == ["7:38", "7:49"]


def test_unknown_or_cancelled():
    assert detail("nope") is None
    gone = LiveTrip("sv1", "SV", True, (), frozenset())
    assert detail(live=gone) is None


def test_station_names_prefer_the_network():
    net = {"stations": [{"codes": ["A01", "C01"], "name": "Metro Center"}]}
    assert station_names(net, {"names": {"C01": "old", "B07": "Takoma"}}) == \
        {"C01": "Metro Center", "A01": "Metro Center", "B07": "Takoma"}


def test_planner_is_unaffected_by_decoding_every_station(fixtures):
    data = (fixtures / "trip_updates.pb").read_bytes()
    every, commute_only = decode_trip_updates(data), decode_trip_updates(data, CommuteConfig().stations)
    assert sum(len(t.stops) for t in every.trips.values()) > sum(len(t.stops) for t in commute_only.trips.values())
    sched = asyncio.run(FixtureSchedule(fixtures / "schedule.json", ET).load())
    now = float(every.feed_timestamp)
    day = scheduled_trips(sched, datetime.fromtimestamp(now, ET).date(), ET)
    for plan in (plan_morning, plan_from_hospital):
        assert plan(merge_trips(day, every, now), CommuteConfig(), now, ET) == \
            plan(merge_trips(day, commute_only, now), CommuteConfig(), now, ET)

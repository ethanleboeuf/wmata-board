from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from wmata_board.commute import (AM, PM, NOTICE_UNAVAILABLE, Rebooking, RideMemory, build_commute, commute_mode, departures,
                                 next_slot, plan_from_hospital, plan_from_station, plan_morning,
                                 plan_to_station)
from wmata_board.config import CommuteConfig
from wmata_board.state import FeedState
from wmata_board.trips import LiveTrip, Stop, Trip, TripUpdates

ET = ZoneInfo("America/New_York")
CFG = CommuteConfig()


def at(hms: str, day: int = 22) -> float:
    """Epoch for H:MM[:SS] on Thursday 2026-10-<day>."""
    parts = [int(x) for x in hms.split(":")] + [0]
    return datetime(2026, 10, day, parts[0], parts[1], parts[2], tzinfo=ET).timestamp()


def trip(tid, line, *calls, live=False):
    """calls: (code, "H:MM[:SS]") -- or (code, arrive, depart)."""
    stops = tuple(Stop(c[0], at(c[1]), at(c[-1])) for c in calls)
    return Trip(tid, line, stops, live)


def orsv(tid, leave, mc, line="SV", **kw):
    return trip(tid, line, ("K01", leave), ("C01", mc), **kw)


def red_in(tid, mc, brookland, **kw):   # toward Glenmont
    return trip(tid, "RD", ("A01", mc), ("B05", brookland), ("B07", "23:59"), **kw)


def red_out(tid, origin_code, origin, mc, **kw):   # toward Shady Grove
    return trip(tid, "RD", (origin_code, origin), ("A01", mc), **kw)


def home_bound(tid, mc, home, line="OR", **kw):
    return trip(tid, line, ("C01", mc), ("K01", home), **kw)


# ---- shuttle slots / windows ---------------------------------------------------

@pytest.mark.parametrize("t, slot", [("8:06", "8:06"), ("8:06:01", "8:12"), ("8:07", "8:12"),
                                     ("8:54:30", "9:00"), ("7:59:59", "8:00")])
def test_next_slot(t, slot):
    assert next_slot(at(t), 6, ET) == at(slot)


@pytest.mark.parametrize("hm, mode", [("6:29", None), ("6:30", AM), ("8:09", AM), ("8:10", None),
                                      ("15:59", None), ("16:00", PM), ("18:29", PM), ("18:30", None)])
def test_mode_windows_on_a_weekday(hm, mode):
    h, m = map(int, hm.split(":"))
    assert commute_mode(CFG, datetime(2026, 10, 22, h, m, tzinfo=ET)) == mode


def test_no_commute_at_weekends():
    assert commute_mode(CFG, datetime(2026, 10, 24, 7, 30, tzinfo=ET)) is None


# ---- legs ------------------------------------------------------------------------

def test_departures_need_both_stops_in_order_and_not_gone():
    trips = [orsv("a", "7:38", "7:49"),
             trip("wrong-way", "SV", ("C01", "7:40"), ("K01", "7:51")),
             orsv("gone", "7:20", "7:31")]
    legs = departures(trips, "K01", "C01", at("7:30"))
    assert [(x.depart, x.arrive) for x in legs] == [(at("7:38"), at("7:49"))]


# ---- morning ---------------------------------------------------------------------

MORNING = [
    orsv("sv738", "7:38", "7:49"),
    orsv("or745", "7:45", "7:55:30", line="OR"),
    orsv("sv748", "7:48", "7:59"),
    red_in("r750", "7:50:30", "8:02"),     # 1.5 min after the 7:49 arrival: too tight
    red_in("r751", "7:51", "8:03"),
    red_in("r757", "7:57:20", "8:09"),     # 1:50 after 7:55:30: missed
    red_in("r801", "8:01", "8:13"),
    red_in("r806", "8:06", "8:18"),
]


def test_morning_rows_connect_on_seconds():
    rows = plan_morning(MORNING, CFG, at("7:30"), ET)
    assert [(r["leave"], r["red_leave"], r["mc_wait"], r["brookland"], r["shuttle"], r["spare"]) for r in rows] == [
        ("7:38", "7:51", 2, "8:03", "8:06", 3),     # 8:03 + 3 min walk = 8:06 exactly
        ("7:45", "8:01", 6, "8:13", "8:18", 5),
        ("7:48", "8:01", 2, "8:13", "8:18", 5),
    ]
    assert [r["target"] for r in rows] == [False, True, True]
    assert rows[0]["line"] == "SV" and rows[1]["line"] == "OR"
    assert rows[0]["mc_arrive"] == "7:49"
    assert rows[0]["legs"] == [{"trip": "sv738", "line": "SV", "from": "K01", "to": "C01"},
                               {"trip": "r751", "line": "RD", "from": "A01", "to": "B05"}]


def test_morning_rows_say_when_to_leave_home():
    rows = plan_morning(MORNING, CFG, at("7:33:30"), ET)
    assert [(r["door"], r["door_in"]) for r in rows] == [("7:32", -1), ("7:39", 6), ("7:42", 9)]
    rows = plan_to_station(MORNING, CFG, at("7:33:30"), ET)
    assert [(r["door"], r["door_in"]) for r in rows] == [("7:32", -1), ("7:39", 6), ("7:42", 9)]


def test_home_walk_is_configurable():
    [row, *_] = plan_morning(MORNING, replace(CFG, home_walk=10), at("7:20"), ET)
    assert (row["door"], row["door_in"]) == ("7:28", 8)


def test_morning_skips_trains_reaching_shuttles_well_before_the_targets():
    early = [orsv("sv700", "7:00", "7:11"), red_in("r715", "7:15", "7:27")]
    assert plan_morning(early + MORNING, CFG, at("6:45"), ET)[0]["leave"] == "7:38"


def test_morning_lists_shuttles_after_the_targets():
    trips = [orsv("sv758", "7:58", "8:09"), red_in("r811", "8:11", "8:23")]
    [row] = plan_morning(trips, CFG, at("7:50"), ET)
    assert (row["shuttle"], row["target"]) == ("8:30", False)


def test_morning_drops_trains_already_gone_and_caps_rows():
    rows = plan_morning(MORNING, replace(CFG, rows=1), at("7:40"), ET)
    assert [r["leave"] for r in rows] == ["7:45"]


def test_morning_row_is_live_only_when_both_trains_are():
    trips = [orsv("a", "7:38", "7:49", live=True), red_in("b", "7:51", "8:03")]
    assert plan_morning(trips, CFG, at("7:30"), ET)[0]["live"] is False
    trips[1] = red_in("b", "7:51", "8:03", live=True)
    assert plan_morning(trips, CFG, at("7:30"), ET)[0]["live"] is True


def test_morning_to_takoma():
    rows = plan_to_station(MORNING, CFG, at("7:30"), ET)
    # red_in reaches B07 at 23:59 in these fixtures; only the connection matters here
    assert [(r["leave"], r["red_leave"], r["mc_wait"]) for r in rows] == [
        ("7:38", "7:51", 2), ("7:45", "8:01", 6), ("7:48", "8:01", 2)]
    assert rows[0]["arrive"] == "11:59"
    assert rows[0]["legs"][1] == {"trip": "r751", "line": "RD", "from": "A01", "to": "B07"}


# ---- evening ---------------------------------------------------------------------

EVENING = [
    red_out("r519", "B05", "17:19", "17:31"),
    red_out("r525", "B05", "17:25", "17:37"),
    red_out("t510", "B07", "17:10", "17:28"),
    home_bound("o533", "17:33", "17:43"),
    home_bound("s540", "17:40", "17:50", line="SV"),
]


def test_evening_from_hospital():
    rows = plan_from_hospital(EVENING, replace(CFG, rows=3), at("17:01"), ET)
    # 17:06 shuttle -> Brookland 17:16, platform by 17:19 -> Red 17:19 -> MC 17:31 -> 17:33 OR (2 min walk)
    assert rows[0] == {"shuttle": "5:06", "brookland": "5:16", "red_leave": "5:19", "mc_arrive": "5:31",
                       "line": "OR", "mc_wait": 2, "home": "5:43", "live": False,
                       "legs": [{"trip": "r519", "line": "RD", "from": "B05", "to": "A01"},
                                {"trip": "o533", "line": "OR", "from": "C01", "to": "K01"}]}
    # 17:12 shuttle -> 17:22 -> Red 17:25 -> MC 17:37 -> 17:40 SV
    assert (rows[1]["shuttle"], rows[1]["red_leave"], rows[1]["line"], rows[1]["home"]) == ("5:12", "5:25", "SV", "5:50")
    assert len(rows) == 2   # nothing for the 17:18 shuttle


def test_evening_from_takoma():
    rows = plan_from_station(EVENING, CFG, at("17:00"), ET)
    assert rows == [{"red_leave": "5:10", "mc_arrive": "5:28", "line": "OR", "mc_wait": 5,
                     "home": "5:43", "live": False,
                     "legs": [{"trip": "t510", "line": "RD", "from": "B07", "to": "A01"},
                              {"trip": "o533", "line": "OR", "from": "C01", "to": "K01"}]}]


# ---- payload ----------------------------------------------------------------------

def schedule_of(trips, start_s=86399):
    """start_s: when each trip leaves its terminal; late by default, so trips the
    live feed doesn't list are still beyond its horizon and kept."""
    return {"names": {"B07": "Takoma"}, "services": {"WK": ["20261022"]},
            "trips": [[t.id, "WK", t.line, start_s,
                       [[s.code, round(s.arrive - at("0:00")), round(s.depart - at("0:00"))] for s in t.stops]]
                      for t in trips]}


def build(now, *, schedule=None, updates=None, updates_age=10.0, mode=None, ride=None, memory=None):
    return build_commute(CFG, schedule=FeedState(value=schedule),
                         updates=FeedState(value=updates, fetched_at=100.0 - updates_age if updates else None),
                         tz=ET, now=now, now_mono=100.0, wall_now=now, mode=mode, ride=ride, memory=memory)


def test_outside_the_windows_there_is_no_panel():
    body = build(at("12:00"), schedule=schedule_of(MORNING))
    assert body["mode"] is None and "am" not in body and "pm" not in body


def test_morning_payload_from_the_timetable():
    body = build(at("7:30"), schedule=schedule_of(MORNING))
    assert body["mode"] == AM and body["live"] is False and body["notice"] is None
    assert body["am"]["shuttles"] == ["8:12", "8:18"]
    assert body["am"]["rows"][0]["shuttle"] == "8:06"
    assert body["am"]["station"][0]["red_leave"] == "7:51"
    assert body["wall_platform"] == "2"


def test_live_predictions_override_the_timetable():
    late = LiveTrip("sv738", "SV", False, (("K01", at("7:41"), at("7:41")), ("C01", at("7:52"), at("7:52"))),
                    frozenset())
    body = build(at("7:30"), schedule=schedule_of(MORNING), updates=TripUpdates(int(at("7:30")), {"sv738": late}))
    first = body["am"]["rows"][0]
    assert body["live"] is True
    assert (first["leave"], first["red_leave"], first["live"]) == ("7:41", "7:57", False)   # Red is timetable


def test_stale_live_data_is_ignored():
    late = LiveTrip("sv738", "SV", False, (("K01", at("7:41"), at("7:41")), ("C01", at("7:52"), at("7:52"))),
                    frozenset())
    body = build(at("7:30"), schedule=schedule_of(MORNING),
                 updates=TripUpdates(int(at("7:30")), {"sv738": late}), updates_age=500)
    assert body["live"] is False
    assert body["am"]["rows"][0]["leave"] == "7:38"


def test_evening_payload_has_both_starts():
    body = build(at("17:01"), schedule=schedule_of(EVENING))
    assert body["mode"] == PM
    assert body["pm"]["station_name"] == "Takoma"
    assert body["pm"]["hospital"][0]["shuttle"] == "5:06"
    assert body["pm"]["station"][0]["red_leave"] == "5:10"


def test_mode_override_and_nothing_to_plan_with():
    body = build(at("12:00"), mode=AM)
    assert body["mode"] == AM and body["notice"] == NOTICE_UNAVAILABLE and "am" not in body


# ---- the ride she's on ------------------------------------------------------------

def live(tid, line, *calls):
    return LiveTrip(tid, line, False, tuple((c, at(t), at(t)) for c, t in calls), frozenset())


def test_ride_row_is_pinned_first_while_listed():
    body = build(at("7:30"), schedule=schedule_of(MORNING), ride=("sv748", "r801"), memory=RideMemory())
    rows = body["am"]["rows"]
    assert [(r["leave"], r.get("riding", False)) for r in rows] == [("7:48", True), ("7:38", False), ("7:45", False)]
    assert body["am"]["station"][0]["leave"] == "7:48" and body["am"]["station"][0]["riding"]


def test_ride_row_stays_after_its_trains_leave_with_the_times_last_seen():
    memory, ride, sched = RideMemory(), ("sv738", "r751"), schedule_of(MORNING)
    early = TripUpdates(int(at("7:30")), {"sv738": live("sv738", "SV", ("K01", "7:38:40"), ("C01", "7:48:50")),
                                          "r751": live("r751", "RD", ("A01", "7:51"), ("B05", "8:03"))})
    assert build(at("7:30"), schedule=sched, updates=early, ride=ride, memory=memory)["am"]["rows"][0]["riding"]
    # 7:56: sv738 has left the feed, r751 is past Metro Center and a minute late to Brookland
    later = TripUpdates(int(at("7:56")), {"r751": live("r751", "RD", ("B05", "8:04"), ("B07", "8:20"))})
    rows = build(at("7:56"), schedule=sched, updates=later, ride=ride, memory=memory)["am"]["rows"]
    pinned = rows[0]
    assert pinned["riding"] and pinned["live"]
    assert (pinned["leave"], pinned["mc_arrive"], pinned["red_leave"], pinned["brookland"], pinned["shuttle"]) == (
        "7:38", "7:48", "7:51", "8:04", "8:12")
    assert (pinned["door"], pinned["door_in"]) == ("7:32", -24)
    assert len(rows) <= CFG.rows


def test_ride_keeps_the_panel_up_past_its_window():
    body = build(at("8:15"), schedule=schedule_of(MORNING), ride=("sv748", "r801"), memory=RideMemory())
    assert body["mode"] == AM
    assert body["am"]["rows"][0]["leave"] == "7:48" and body["am"]["rows"][0]["riding"]
    assert build(at("8:15"), schedule=schedule_of(MORNING))["mode"] is None


def test_evening_ride_keeps_the_shuttle_she_was_planned_onto():
    memory, ride = RideMemory(), ("r519", "o533")
    first = build(at("17:01"), schedule=schedule_of(EVENING), ride=ride, memory=memory)["pm"]["hospital"][0]
    assert (first["shuttle"], first["riding"]) == ("5:06", True)
    pinned = build(at("17:35"), schedule=schedule_of(EVENING), ride=ride, memory=memory)["pm"]["hospital"][0]
    assert (pinned["shuttle"], pinned["brookland"], pinned["red_leave"], pinned["home"]) == ("5:06", "5:16", "5:19", "5:43")


def test_a_red_train_off_the_map_pins_the_row_it_ends():
    # On r801 (tapped on the map): the last Orange/Silver that made it was sv748 (7:59 + 2 min walk)
    rows = build(at("8:05"), schedule=schedule_of(MORNING), ride=("r801",), memory=RideMemory())["am"]["rows"]
    assert (rows[0]["leave"], rows[0]["red_leave"], rows[0]["shuttle"], rows[0]["riding"]) == ("7:48", "8:01", "8:18", True)
    assert [l["trip"] for l in rows[0]["legs"]] == ["sv748", "r801"]
    assert not any(r.get("riding") for r in rows[1:])


def test_an_orange_silver_train_off_the_map_pins_the_row_it_starts():
    rows = build(at("7:30"), schedule=schedule_of(MORNING), ride=("or745",), memory=RideMemory())["am"]["rows"]
    assert (rows[0]["leave"], rows[0]["red_leave"], rows[0]["riding"]) == ("7:45", "8:01", True)
    assert sum(bool(r.get("riding")) for r in rows) == 1


def test_an_evening_red_train_off_the_map():
    hospital = build(at("17:20"), schedule=schedule_of(EVENING), ride=("r525",), memory=RideMemory())["pm"]["hospital"]
    assert (hospital[0]["red_leave"], hospital[0]["line"], hospital[0]["home"], hospital[0]["riding"]) == (
        "5:25", "SV", "5:50", True)


def test_a_late_first_train_moves_the_ride_to_the_next_red_it_makes():
    # sv748 was to make the 8:01 Red with 2 min to spare; it now reaches Metro Center at 8:00:30
    memory, ride = RideMemory(), ("sv748", "r801")
    late = TripUpdates(int(at("7:50")), {"sv748": live("sv748", "SV", ("K01", "7:50"), ("C01", "8:00:30"))})
    rows = build(at("7:50"), schedule=schedule_of(MORNING), updates=late, ride=ride, memory=memory)["am"]["rows"]
    assert (rows[0]["red_leave"], rows[0]["brookland"], rows[0]["shuttle"], rows[0]["riding"]) == (
        "8:06", "8:18", "8:24", True)
    assert rows[0]["note"] == "Missed the 8:01 Red — now the 8:06"
    assert [l["trip"] for l in rows[0]["legs"]] == ["sv748", "r806"]
    assert not any(r.get("note") for r in rows[1:])
    # the app moves the ride (and the rider) onto the new train
    assert memory.rebooked == Rebooking(("sv748", "r806"), at("8:00:30"), at("8:18"), rows[0]["note"])
    # ...and once it has, the note stays and nothing resets
    memory.rebooked = None
    again = build(at("7:55"), schedule=schedule_of(MORNING), updates=late, ride=("sv748", "r806"), memory=memory)
    assert again["am"]["rows"][0]["note"] == "Missed the 8:01 Red — now the 8:06" and memory.rebooked is None


def test_a_connection_still_made_by_a_hurry_stays():
    memory, ride = RideMemory(), ("sv748", "r801")
    late = TripUpdates(int(at("7:50")), {"sv748": live("sv748", "SV", ("K01", "7:50"), ("C01", "7:59:59"))})
    rows = build(at("7:50"), schedule=schedule_of(MORNING), updates=late, ride=ride, memory=memory)["am"]["rows"]
    assert rows[0]["red_leave"] == "8:01" and "note" not in rows[0] and memory.rebooked is None


def test_an_evening_ride_moves_to_the_next_train_home_naming_its_line():
    memory, ride = RideMemory(), ("r519", "o533")
    late = TripUpdates(int(at("17:20")), {"r519": live("r519", "RD", ("B05", "17:21"), ("A01", "17:34"))})
    row = build(at("17:20"), schedule=schedule_of(EVENING), updates=late, ride=ride, memory=memory)["pm"]["hospital"][0]
    assert (row["line"], row["home"], row["riding"]) == ("SV", "5:50", True)
    assert row["note"] == "Missed the 5:33 Orange — now the 5:40 Silver"


def test_a_one_train_ride_keeps_the_panel_only_a_while_on_weekdays():
    sched = schedule_of(MORNING)
    assert build(at("10:00"), schedule=sched, ride=("r801",))["am"]["rows"][0]["riding"]
    assert build(at("10:30"), schedule=sched, ride=("r801",))["mode"] is None


def test_a_train_that_fits_no_commute_pins_nothing():
    stray = trip("gr1", "GR", ("E01", "7:40"), ("F01", "7:50"))
    body = build(at("7:30"), schedule=schedule_of(MORNING + [stray]), ride=("gr1",), memory=RideMemory())
    assert not any(r.get("riding") for r in body["am"]["rows"])
    assert build(at("12:00"), schedule=schedule_of(MORNING + [stray]), ride=("gr1",))["mode"] is None


# ---- alerts -----------------------------------------------------------------------

def test_commute_alerts_cover_red_and_expire():
    from wmata_board.commute import commute_alerts
    from wmata_board.incidents import Alert

    alerts = [Alert("1", ("RD",), "Red: single tracking", "t"), Alert("2", ("OR", "SV"), "OR/SV delays", "t"),
              Alert("3", ("GR", "YL"), "Green/Yellow", "t")]
    fresh = FeedState(value=alerts, fetched_at=90.0)
    assert [a["id"] for a in commute_alerts(CFG, fresh, 100.0)] == ["1", "2"]
    assert commute_alerts(CFG, FeedState(value=alerts, fetched_at=0.0), 1000.0) == []
    assert commute_alerts(CFG, FeedState(), 100.0) == []
    body = build_commute(CFG, schedule=FeedState(value=schedule_of(MORNING)), updates=FeedState(), tz=ET,
                         now=at("7:30"), now_mono=100.0, wall_now=at("7:30"), incidents=fresh)
    assert [a["id"] for a in body["alerts"]] == ["1", "2"]

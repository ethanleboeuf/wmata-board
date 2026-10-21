from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from wmata_board.commute import (AM, PM, NOTICE_UNAVAILABLE, build_commute, commute_mode, departures,
                                 next_slot, plan_from_hospital, plan_from_station, plan_morning)
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
    assert not any(r["late"] for r in rows)
    assert rows[0]["line"] == "SV" and rows[1]["line"] == "OR"
    assert rows[0]["mc_arrive"] == "7:49"
    assert rows[0]["legs"] == [{"trip": "sv738", "line": "SV", "from": "K01", "to": "C01"},
                               {"trip": "r751", "line": "RD", "from": "A01", "to": "B05"}]


def test_morning_skips_trains_reaching_shuttles_well_before_the_targets():
    early = [orsv("sv700", "7:00", "7:11"), red_in("r715", "7:15", "7:27")]
    assert plan_morning(early + MORNING, CFG, at("6:45"), ET)[0]["leave"] == "7:38"


def test_morning_flags_shuttles_after_the_targets():
    trips = [orsv("sv758", "7:58", "8:09"), red_in("r811", "8:11", "8:23")]
    [row] = plan_morning(trips, CFG, at("7:50"), ET)
    assert (row["shuttle"], row["target"], row["late"]) == ("8:30", False, True)


def test_morning_drops_trains_already_gone_and_caps_rows():
    rows = plan_morning(MORNING, replace(CFG, rows=1), at("7:40"), ET)
    assert [r["leave"] for r in rows] == ["7:45"]


def test_morning_row_is_live_only_when_both_trains_are():
    trips = [orsv("a", "7:38", "7:49", live=True), red_in("b", "7:51", "8:03")]
    assert plan_morning(trips, CFG, at("7:30"), ET)[0]["live"] is False
    trips[1] = red_in("b", "7:51", "8:03", live=True)
    assert plan_morning(trips, CFG, at("7:30"), ET)[0]["live"] is True


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


def build(now, *, schedule=None, updates=None, updates_age=10.0, mode=None):
    return build_commute(CFG, schedule=FeedState(value=schedule),
                         updates=FeedState(value=updates, fetched_at=100.0 - updates_age if updates else None),
                         tz=ET, now=now, now_mono=100.0, wall_now=now, mode=mode)


def test_outside_the_windows_there_is_no_panel():
    body = build(at("12:00"), schedule=schedule_of(MORNING))
    assert body["mode"] is None and "am" not in body and "pm" not in body


def test_morning_payload_from_the_timetable():
    body = build(at("7:30"), schedule=schedule_of(MORNING))
    assert body["mode"] == AM and body["live"] is False and body["notice"] is None
    assert body["am"]["shuttles"] == ["8:12", "8:18"]
    assert body["am"]["rows"][0]["shuttle"] == "8:06"
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

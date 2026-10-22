from datetime import datetime

from helpers import (ET, NOON, arrivals_state, config, incidents_state,
                     station_state, state)

from wmata_board.board import (NOTICE_BAD_KEY, NOTICE_LOADING, NOTICE_NO_KEY,
                               NOTICE_UNAVAILABLE, build_board)
from wmata_board.state import FeedState


def board(cfg=None, arrivals=None, incidents=None, station=None, now=110.0, now_local=NOON, other=None):
    return build_board(config=cfg or config(), arrivals=arrivals or arrivals_state(),
                       incidents=incidents or incidents_state(), station=station or station_state(),
                       now=now, now_local=now_local, version="v1", other=other)


def test_normal_board():
    b = board()
    assert b["station"] == {"code": "K01", "name": "Court House", "home": True}
    assert b["timezone"] == "America/New_York"
    assert b["version"] == "v1"
    assert b["notice"] is None
    assert [p["label"] for p in b["platforms"]] == ["To Washington · New Carrollton", "To Vienna · Ashburn"]
    east = b["platforms"][0]["trains"]
    assert [t["display"] for t in east] == ["2", "10", "26"]
    assert east[0]["destination"] == "New Carrollton"
    assert b["service"] == {"first_train": "5:19 AM", "last_train": "12:20 AM"}
    assert [a["lines"] for a in b["alerts"]] == [["OR", "SV"], ["BL", "OR", "SV"]]
    assert b["freshness"]["arrivals"] == {"age_s": 10, "stale": False, "error": None}
    assert b["generated_at"].startswith("2026-10-20T12:00")


def test_stale_flag_after_60s():
    assert board(now=161.0)["freshness"]["arrivals"]["stale"] is True


def test_unavailable_after_ten_minutes():
    b = board(now=100.0 + 601)
    assert b["notice"] == NOTICE_UNAVAILABLE
    assert all(p["trains"] == [] for p in b["platforms"])


def test_no_key():
    b = board(cfg=config(api_key=None), arrivals=FeedState(error="x", error_kind="no_key"))
    assert b["notice"] == NOTICE_NO_KEY


def test_bad_key_before_any_data():
    b = board(arrivals=FeedState(error="401", error_kind="api_key"))
    assert b["notice"] == NOTICE_BAD_KEY


def test_loading_before_first_fetch():
    assert board(arrivals=FeedState())["notice"] == NOTICE_LOADING


def test_network_error_before_any_data():
    assert board(arrivals=FeedState(error="down", error_kind="network"))["notice"] == NOTICE_UNAVAILABLE


def test_error_after_good_data_keeps_trains_and_reports_error():
    b = board(arrivals=arrivals_state(error="down", error_kind="network"))
    assert b["notice"] is None
    assert b["freshness"]["arrivals"]["error"] == "network"
    assert b["platforms"][0]["trains"]


def test_closed_station_says_when_service_resumes():
    late = datetime(2026, 10, 20, 0, 45, tzinfo=ET)
    b = board(arrivals=state([]), now_local=late)
    assert b["notice"] == "No trains · service resumes 5:19 AM"


def test_no_trains_during_service_hours_is_not_closed():
    b = board(arrivals=state([]))
    assert b["notice"] is None
    assert all(p["trains"] == [] for p in b["platforms"])


def test_station_info_missing_falls_back():
    b = board(station=FeedState())
    assert b["station"]["name"] == "K01"
    assert b["service"] is None
    assert b["notice"] is None


def test_lines_omitted_uses_station_lines(tmp_path):
    from wmata_board.config import load_config
    path = tmp_path / "config.toml"
    path.write_text('[board]\nstations = ["K01"]\n', encoding="utf-8")
    cfg = load_config(path, environ={"WMATA_API_KEY": "k"})
    b = board(cfg=cfg)
    assert {a["id"][-1] for a in b["alerts"]} == {"1", "3"}     # RD alert filtered via station lines


def test_incidents_never_fetched():
    b = board(incidents=FeedState())
    assert b["alerts"] == []
    assert b["freshness"]["incidents"]["age_s"] is None


def test_bad_key_after_good_data():
    # key rejected mid-run: once the last good value is > 60 s old, say so
    b = board(arrivals=arrivals_state(error="401", error_kind="api_key"), now=100.0 + 61)
    assert b["notice"] == NOTICE_BAD_KEY
    assert all(p["trains"] == [] for p in b["platforms"])


def test_fresh_value_with_just_failed_api_key_fetch_still_shows_trains():
    b = board(arrivals=arrivals_state(error="401", error_kind="api_key"), now=100.0 + 30)
    assert b["notice"] is None
    assert b["platforms"][0]["trains"]


def test_alerts_dropped_when_incident_feed_older_than_15_min():
    assert board(incidents=incidents_state(), now=100.0 + 899)["alerts"]
    assert board(incidents=incidents_state(), now=100.0 + 901)["alerts"] == []


def test_any_station_with_every_platform_of_a_transfer_station():
    from wmata_board.board import NOTICE_NO_TRAINS
    from wmata_board.predictions import parse_predictions

    raw = lambda loc, group, line, dest, m: {"LocationCode": loc, "Group": group, "Line": line, "Car": "8",
                                             "Destination": dest, "DestinationName": dest, "Min": m}
    trains = parse_predictions({"Trains": [raw("A01", "1", "RD", "Glenmont", "3"), raw("A01", "2", "RD", "Shady Grv", "5"),
                                           raw("C01", "1", "BL", "Largo", "ARR"), raw("K01", "1", "OR", "NewCrltn", "2")]},
                               None)
    mc = {"codes": ["A01", "C01"], "name": "Metro Center"}
    b = board(arrivals=state(trains), other=mc)
    assert b["station"] == {"code": "A01", "name": "Metro Center", "home": False}
    assert [p["label"] for p in b["platforms"]] == ["To Glenmont", "To Shady Grv", "To Largo"]
    assert b["service"] is None and b["notice"] is None
    assert {l for a in b["alerts"] for l in a["lines"]} & {"RD", "BL"}
    assert board(arrivals=state(trains), other={"codes": ["N06"], "name": "Wiehle"})["notice"] == NOTICE_NO_TRAINS

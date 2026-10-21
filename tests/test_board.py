from datetime import datetime

from helpers import (ET, NOON, arrivals_state, config, incidents_state,
                     station_state, state)

from wmata_board.board import (NOTICE_BAD_KEY, NOTICE_LOADING, NOTICE_NO_KEY,
                               NOTICE_UNAVAILABLE, build_board)
from wmata_board.state import FeedState


def board(cfg=None, arrivals=None, incidents=None, station=None, now=110.0, now_local=NOON):
    return build_board(config=cfg or config(), arrivals=arrivals or arrivals_state(),
                       incidents=incidents or incidents_state(), station=station or station_state(),
                       now=now, now_local=now_local, version="v1")


def test_normal_board():
    b = board()
    assert b["station"] == {"code": "K01", "name": "Court House"}
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

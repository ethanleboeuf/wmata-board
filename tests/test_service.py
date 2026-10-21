import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from wmata_board.service import clock_label, service_status, station_data
from wmata_board.wmata import WmataError

ET = ZoneInfo("America/New_York")


@pytest.fixture
def times(fixtures):
    return json.loads((fixtures / "station_times_K01.json").read_text(encoding="utf-8"))


@pytest.fixture
def info(fixtures):
    return json.loads((fixtures / "station_info_K01.json").read_text(encoding="utf-8"))


def at(y, mo, d, h, mi):
    return datetime(2026, mo, d, h, mi, tzinfo=ET) if y is None else datetime(y, mo, d, h, mi, tzinfo=ET)


def test_station_data(info, times):
    s = station_data("K01", info, times)
    assert (s.code, s.name, s.lines) == ("K01", "Court House", ("OR", "SV"))
    assert s.times is times


def test_station_data_tolerates_missing_name(times):
    assert station_data("K01", {}, times).name == "K01"


@pytest.mark.parametrize("h, mi, label", [(5, 19, "5:19 AM"), (0, 20, "12:20 AM"), (12, 0, "12:00 PM"), (23, 5, "11:05 PM")])
def test_clock_label(h, mi, label):
    assert clock_label(at(None, 10, 20, h, mi)) == label


# 2026-10-20 is a Tuesday. Weekday trains: first 05:19, last 00:20 (next day).
def test_midday_in_service(times):
    s = service_status(times, "K01", at(None, 10, 20, 12, 0))
    assert s.in_service and s.resumes is None
    assert (s.first_train, s.last_train) == ("5:19 AM", "12:20 AM")


def test_just_after_midnight_still_previous_service_day(times):
    assert service_status(times, "K01", at(None, 10, 20, 0, 10)).in_service


def test_after_last_train_resumes_same_morning(times):
    s = service_status(times, "K01", at(None, 10, 20, 0, 30))
    assert not s.in_service
    assert s.resumes == "5:19 AM"


def test_early_morning_before_first_train(times):
    s = service_status(times, "K01", at(None, 10, 20, 4, 30))
    assert not s.in_service and s.resumes == "5:19 AM"


def test_friday_night_runs_late(times):
    # Sat 2026-10-24 01:30 belongs to Friday's service day (last train 02:20)
    assert service_status(times, "K01", at(None, 10, 24, 1, 30)).in_service


def test_saturday_resumes_at_saturday_first_train(times):
    # Sat 03:00: Friday's service is over; Saturday's earliest first train is 06:14
    s = service_status(times, "K01", at(None, 10, 24, 3, 0))
    assert not s.in_service and s.resumes == "6:14 AM"


def test_unknown_station_raises(times):
    with pytest.raises(WmataError):
        service_status(times, "Z99", at(None, 10, 20, 12, 0))


def test_missing_day_returns_none():
    payload = {"StationTimes": [{"Code": "K01"}]}
    assert service_status(payload, "K01", at(None, 10, 20, 12, 0)) is None

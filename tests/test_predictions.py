import json

import pytest

from wmata_board.predictions import (NO_TIME, destination_of, parse_predictions,
                                     platforms_for)
from wmata_board.wmata import WmataError


def raw(**kw):
    base = {"Car": "8", "Destination": "Vienna", "DestinationCode": "K08",
            "DestinationName": "Vienna/Fairfax-GMU", "Group": "2", "Line": "OR",
            "LocationCode": "K01", "LocationName": "Court House", "Min": "5"}
    base.update(kw)
    return base


def parse(*trains, lines=None):
    return parse_predictions({"Trains": list(trains)}, ["K01"], lines)


def test_recorded_k01_response(fixtures):
    payload = json.loads((fixtures / "predictions_K01.json").read_text(encoding="utf-8"))
    trains = parse_predictions(payload, ["K01"])
    assert len(trains) == 6
    first = trains[0]
    assert (first.line, first.cars, first.destination, first.minutes, first.display) == \
        ("SV", 6, "New Carrollton", 2, "2")
    assert {t.destination for t in trains} == {"New Carrollton", "Ashburn", "Vienna/Fairfax-GMU"}


def test_recorded_late_response_last_train(fixtures):
    payload = json.loads((fixtures / "predictions_K01_late.json").read_text(encoding="utf-8"))
    dests = [t.destination for t in parse_predictions(payload, ["K01"])]
    assert "Last train" in dests
    assert "LastTrain" not in dests


@pytest.mark.parametrize("fields, expected", [
    ({}, "Vienna/Fairfax-GMU"),                                        # code set -> DestinationName
    ({"DestinationCode": None, "DestinationName": "NewCrlton", "Destination": "NewCrlton"}, "New Carrollton"),
    ({"DestinationCode": None, "DestinationName": "LastTrain", "Destination": "LastTrain"}, "Last train"),
    ({"DestinationCode": None, "DestinationName": "Odd", "Destination": "Oddville"}, "Oddville"),
    ({"DestinationCode": "", "DestinationName": "", "Destination": ""}, "Train"),
    ({"DestinationCode": None, "DestinationName": None, "Destination": None}, "Train"),
])
def test_destination_rules(fields, expected):
    assert destination_of(raw(**fields)) == expected


@pytest.mark.parametrize("value, minutes, display", [
    ("5", 5, "5"), ("12", 12, "12"), ("ARR", 0, "ARR"), ("BRD", 0, "BRD"),
    ("---", None, NO_TIME), ("", None, NO_TIME), (None, None, NO_TIME),
])
def test_minutes(value, minutes, display):
    (t,) = parse(raw(Min=value))
    assert (t.minutes, t.display) == (minutes, display)


@pytest.mark.parametrize("fields", [
    {"Line": ""}, {"Line": "No"}, {"Line": "--"}, {"Line": None},
    {"Destination": "No Passenger", "DestinationName": "No Passenger"},
    {"Destination": "ssenger", "DestinationName": "ssenger"},
])
def test_no_passenger_trains_dropped(fields):
    assert parse(raw(**fields)) == []


def test_other_stations_and_lines_dropped():
    trains = parse(raw(LocationCode="C05"), raw(Line="BL"), raw(), lines=["OR", "SV"])
    assert len(trains) == 1


def test_cars_unknown_is_none():
    (t,) = parse(raw(Car="-"))
    assert t.cars is None


def test_bad_payload_raises_parse():
    with pytest.raises(WmataError) as err:
        parse_predictions({"oops": 1}, ["K01"])
    assert err.value.kind == "parse"


def test_non_dict_entries_skipped():
    assert len(parse_predictions({"Trains": [None, "x", raw()]}, ["K01"])) == 1


def test_platform_order_and_rows():
    trains = parse(raw(Min="7"), raw(Min="ARR"), raw(Min="---"), raw(Min="BRD"), raw(Min="2"))
    (p,) = platforms_for(trains, "K01", {"2": "To Vienna · Ashburn"}, rows=10)
    assert [t.display for t in p.trains] == ["BRD", "ARR", "2", "7", NO_TIME]
    assert p.label == "To Vienna · Ashburn"
    (p3,) = platforms_for(trains, "K01", {"2": "x"}, rows=3)
    assert [t.display for t in p3.trains] == ["BRD", "ARR", "2"]


def test_configured_platforms_always_listed_in_group_order():
    trains = parse(raw(Group="1", Min="3"))
    ps = platforms_for(trains, "K01", {"2": "West", "1": "East"}, rows=3)
    assert [(p.group, p.label, len(p.trains)) for p in ps] == [("1", "East", 1), ("2", "West", 0)]


def test_unconfigured_group_gets_destination_label():
    trains = parse(raw(Group="3", DestinationName="Ashburn", Min="1"),
                   raw(Group="3", DestinationName="Vienna/Fairfax-GMU", Min="2"),
                   raw(Group="3", DestinationName="Ashburn", Min="3"))
    (p,) = platforms_for(trains, "K01", {}, rows=3)
    assert p.label == "To Ashburn · Vienna/Fairfax-GMU"


def test_as_json_shapes():
    (t,) = parse(raw())
    assert t.as_json() == {"line": "OR", "cars": 8, "destination": "Vienna/Fairfax-GMU",
                           "minutes": 5, "display": "5"}
    (p,) = platforms_for([t], "K01", {}, rows=3)
    assert p.as_json()["trains"] == [t.as_json()]

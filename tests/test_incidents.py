import json

import pytest

from wmata_board.incidents import affected_lines, alerts_for, parse_incidents
from wmata_board.wmata import WmataError


@pytest.mark.parametrize("s, expected", [
    ("OR; SV;", ("OR", "SV")), ("RD;", ("RD",)), ("BL;OR;SV;", ("BL", "OR", "SV")),
    ("or ;sv", ("OR", "SV")), ("", ()), (None, ()), ("OR; OR;", ("OR",)),
])
def test_affected_lines(s, expected):
    assert affected_lines(s) == expected


def test_empty_feed(fixtures):
    payload = json.loads((fixtures / "incidents_empty.json").read_text(encoding="utf-8"))
    assert parse_incidents(payload) == []


def test_sample_feed_filtering(fixtures):
    alerts = parse_incidents(json.loads((fixtures / "incidents.json").read_text(encoding="utf-8")))
    assert len(alerts) == 3
    mine = alerts_for(alerts, ["OR", "SV"])
    assert [a.lines for a in mine] == [("OR", "SV"), ("BL", "OR", "SV")]
    assert alerts_for(alerts, ["YL"]) == []
    assert alerts_for(alerts, None) == alerts


def test_alert_json(fixtures):
    (a, *_) = parse_incidents(json.loads((fixtures / "incidents.json").read_text(encoding="utf-8")))
    assert a.as_json() == {"id": "A1B2C3D4-0000-4000-8000-000000000001", "lines": ["OR", "SV"],
                           "text": a.text, "updated": "2026-10-20T21:58:12"}


def test_blank_description_skipped():
    assert parse_incidents({"Incidents": [{"IncidentID": "x", "Description": " ", "LinesAffected": "OR;"}]}) == []


def test_missing_id_falls_back_to_text():
    (a,) = parse_incidents({"Incidents": [{"Description": "Something", "LinesAffected": "OR;"}]})
    assert a.id == "Something"


def test_bad_payload():
    with pytest.raises(WmataError):
        parse_incidents([])

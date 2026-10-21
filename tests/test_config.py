from pathlib import Path

import pytest

from wmata_board.config import ConfigError, load_config

from conftest import REPO


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_repo_config_loads():
    config = load_config(REPO / "config.toml", environ={})
    assert config.board.stations == ("K01",)
    assert config.board.station == "K01"
    assert config.board.lines == ("OR", "SV")
    assert config.board.rows_per_direction == 3
    assert config.platforms["K01"]["1"] == "To Washington · New Carrollton"
    assert config.polling.arrivals == 20
    assert config.polling.idle_after == 90
    assert config.map.bbox == (-77.122, 38.844, -76.978, 38.966)
    assert config.map.labels[0] == "K04"
    assert config.map.places[0].name == "GEORGETOWN"
    assert config.map.places[0].lat == pytest.approx(38.9085)
    assert config.map.landmarks[0].name == "Children's National"
    assert config.map.landmarks[0].style == "hospital"
    assert (config.server.host, config.server.port) == ("127.0.0.1", 8766)


def test_defaults_when_sections_missing(tmp_path):
    config = load_config(write(tmp_path, ""), environ={})
    assert config.board.stations == ("K01",)
    assert config.board.lines is None
    assert config.board.timezone == "America/New_York"
    assert config.platforms == {}
    assert config.polling.positions == 5
    assert config.server.port == 8766


def test_station_codes_are_uppercased(tmp_path):
    config = load_config(write(tmp_path, '[board]\nstations = ["k01"]\n'), environ={})
    assert config.board.stations == ("K01",)


@pytest.mark.parametrize("text, match", [
    ('[board]\nstations = []\n', "stations"),
    ('[board]\nstations = ["Court House"]\n', "station code"),
    ('[board]\nlines = ["PK"]\n', "unknown line"),
    ('[board]\nrows_per_direction = 0\n', "rows_per_direction"),
    ('[board]\nrows_per_direction = true\n', "rows_per_direction"),
    ('[board]\ntimezone = "Mars/Olympus"\n', "timezone"),
    ('[polling]\narrivals = 0\n', "arrivals"),
    ('[polling]\npositions = "fast"\n', "positions"),
    ('[map]\nbbox = [1, 2, 3]\n', "bbox"),
    ('[map]\nbbox = [-76, 38.8, -77, 38.9]\n', "bbox"),
    ('[map]\nplaces = [["X", 38.9]]\n', "places"),
    ('[[map.landmarks]]\nname = "X"\n', "landmarks"),
    ('[server]\nport = 70000\n', "port"),
    ('[board\n', "config.toml"),
])
def test_bad_values_raise(tmp_path, text, match):
    with pytest.raises(ConfigError, match=match):
        load_config(write(tmp_path, text), environ={})


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml", environ={})


def test_api_key_from_environment(tmp_path):
    config = load_config(write(tmp_path, ""), environ={"WMATA_API_KEY": " abc123 "})
    assert config.api_key == "abc123"


def test_api_key_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text('# comment\nexport WMATA_API_KEY="fromfile"\n', encoding="utf-8")
    config = load_config(write(tmp_path, ""), environ={})
    assert config.api_key == "fromfile"


def test_environment_beats_dotenv(tmp_path):
    (tmp_path / ".env").write_text("WMATA_API_KEY=fromfile\n", encoding="utf-8")
    config = load_config(write(tmp_path, ""), environ={"WMATA_API_KEY": "fromenv"})
    assert config.api_key == "fromenv"


def test_no_key_is_none(tmp_path):
    assert load_config(write(tmp_path, ""), environ={}).api_key is None


def test_repr_never_shows_key(tmp_path):
    config = load_config(write(tmp_path, ""), environ={"WMATA_API_KEY": "s3cret-key"})
    assert "s3cret-key" not in repr(config)


def test_repo_commute_config():
    c = load_config(REPO / "config.toml", environ={}).commute
    assert c is not None
    assert (c.home, c.transfer, c.shuttle_stop, c.evening_from) == ("K01", ("C01", "A01"), "B05", "B07")
    assert c.morning == (6 * 60 + 30, 8 * 60 + 10)
    assert c.evening == (16 * 60, 18 * 60 + 30)
    assert c.shuttles == (8 * 60 + 12, 8 * 60 + 18)
    assert (c.shuttle_every, c.shuttle_ride, c.transfer_walk, c.shuttle_walk) == (6, 10, 2, 3)
    assert c.stations == ("K01", "C01", "A01", "B05", "B07")


def test_commute_is_optional(tmp_path):
    assert load_config(write(tmp_path, ""), environ={}).commute is None


@pytest.mark.parametrize("body, msg", [
    ('morning = ["8:10", "6:30"]', "start must be before end"),
    ('morning = ["6:30"]', r"must be \[start, end\]"),
    ('shuttles = ["8:75"]', "not a time"),
    ('shuttle_every = 7', "divides 60"),
    ('transfer = ["C01"]', "transfer must be"),
    ('home = "Court House"', "not a station code"),
    ('transfer_walk = -1', "0-60"),
])
def test_commute_validation(tmp_path, body, msg):
    with pytest.raises(ConfigError, match=msg):
        load_config(write(tmp_path, f"[commute]\n{body}\n"), environ={})

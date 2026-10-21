"""Shared builders for board/app tests."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from wmata_board.config import load_config
from wmata_board.incidents import parse_incidents
from wmata_board.predictions import parse_predictions
from wmata_board.service import station_data
from wmata_board.state import FeedState

from conftest import FIXTURES, REPO

ET = ZoneInfo("America/New_York")
NOON = datetime(2026, 10, 20, 12, 0, tzinfo=ET)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def config(api_key="k"):
    return load_config(REPO / "config.toml", environ={"WMATA_API_KEY": api_key} if api_key else {})


def state(value, fetched_at=100.0, error=None, error_kind=None):
    return FeedState(value=value, fetched_at=fetched_at, error=error, error_kind=error_kind)


def arrivals_state(name="predictions_K01.json", **kw):
    return state(parse_predictions(load(name), ["K01"]), **kw)


def incidents_state(name="incidents.json", **kw):
    return state(parse_incidents(load(name)), **kw)


def station_state(**kw):
    return state(station_data("K01", load("station_info_K01.json"), load("station_times_K01.json")), **kw)

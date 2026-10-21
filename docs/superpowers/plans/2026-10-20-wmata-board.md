# WMATA Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A glanceable Court House (K01) departure board — live arrivals, line alerts and a live train map — served by one FastAPI process on the Pi, shown on the wall kiosk via kiosk-selector and on a phone over Tailscale.

**Architecture:** One asyncio process. Each WMATA feed (arrivals, incidents, station info/times, train positions, GTFS-static network) is a `Feed` task with its own cadence, demand gating and backoff, holding last-known state. Pure modules turn raw WMATA payloads into small dataclasses; `board.py` assembles the `/api/board` JSON. The browser side is vanilla ES modules: pure helpers (`format.js`, `render.js`, `track.js`, tested with `node --test`) plus DOM glue (`board.js`, `map.js`, `phone.js`). MapLibre draws only the self-hosted Protomaps basemap; tracks, stations and trains are an SVG overlay re-projected with `map.project()`.

**Tech Stack:** Python 3.12+/3.13 (Pi runs 3.13.5, dev PC 3.12.10), FastAPI, uvicorn, httpx, gtfs-realtime-bindings, tomllib, pytest + pytest-asyncio; vanilla JS ES modules, MapLibre GL JS 4.7.1 + pmtiles 3.2.1 (vendored), Inter (vendored woff2), Node 24 `node --test` for JS unit tests.

**Spec:** `docs/superpowers/specs/2026-10-20-wmata-board-design.md` — read it alongside this plan.

## Global Constraints

- Code must run on Python 3.12 (dev PC) and 3.13 (Pi): `requires-python = ">=3.12"`, no 3.13-only syntax.
- Package `wmata_board` in `src/` layout; entry point `python -m wmata_board --config config.toml`; `--fixtures DIR` runs with no network/key.
- The API key (`WMATA_API_KEY`) is never printed, logged, put in an error message, or committed. It comes from the environment (systemd `EnvironmentFile=%h/wmata-board.env`) or a gitignored `.env` next to the config file. `Config.api_key` has `repr=False`.
- WMATA auth is the `api_key` request header; client timeout 8 s.
- Cadences (seconds): arrivals 20, incidents 60, positions 5, idle_after 90; backoff cadence × 2ⁿ capped at 300 s, reset on success.
- No exception escapes a feed task; the process never exits because WMATA is down; missing key → service starts and board says "No WMATA API key configured".
- Staleness: amber pill "Updated N min ago" when arrivals > 60 s old; red "Board offline" when the browser can't reach the backend (> 15 s without a good response); arrivals > 600 s old replaced by "Live arrivals unavailable"; map trains fade when positions > 120 s old.
- Palette: page `#0d1117`, ARR/BRD `#ffd166`; Board navy map: land `#0f151d`, water `#0c2742`, minor features `#151e29`, streets `#24324a`, major streets `#33465f`, place labels `#3b4a5e`.
- Line colors (from WMATA GTFS routes.txt): RD `#c80f2d`/white text, OR `#ed8b00`/dark, SV `#919d9d`/dark, BL `#009cde`/white, GR `#00b140`/white, YL `#ffd100`/dark.
- Lane offsets in line widths (LW = 7 px): RD 0, OR −0.5, SV +0.5, BL +1.5, GR −0.5, YL +0.5. Draw order RD, GR, YL, BL, OR, SV.
- Train marker = "badge": glow halo in line color, line-color bullet (r 10.5, white 2 px stroke) with the line letter (R/O/S/B/G/Y; dark text on OR/SV/YL), white heading arrowhead.
- Line vocabulary everywhere in our own JSON: WMATA two-letter codes `RD OR SV BL GR YL` (GTFS route_ids `RED ORANGE …` are mapped on ingest).
- Server binds `127.0.0.1:8766`. Phone view at `https://raspberrypi.tail7b0b4d.ts.net:8446/phone` via `tailscale serve --bg --https=8446 http://127.0.0.1:8766`.
- All browser assets local (no CDN at runtime). Basemap attribution "© OpenStreetMap contributors" visible.
- Local commands use the Windows venv: `.venv/Scripts/python -m pytest` (on the Pi: `.venv/bin/python`). JS tests: `node --test tests/js/`.
- Commit messages end with the attribution lines given in the session's system reminder.

## Review Focus

1. **Destination quirks** — WMATA sends `DestinationCode: null` with abbreviated names (`NewCrlton`, and late at night `LastTrain`, recorded 2026-10-20 in `tests/fixtures/predictions_K01_late.json`). Expect "New Carrollton" / "Last train", never a raw code. Test in Task 3.
2. **After-midnight service window** — last trains at 00:20 (02:20 Fri/Sat) belong to the previous service day; at 00:10 Tuesday the station is still in service, at 00:30 it says "resumes 5:19 AM". Tests in Task 4.
3. **First request after idle** — opening the board after hours on skyview must not show 10-minute-old minutes for 5 s; `/api/board` waits (≤ 3 s) for a fresh fetch when the feed was idle and due. Test in Task 7.
4. **Feed timestamp unchanged / going backwards** — positions polled every 5 s often return the same snapshot, and fixtures mode wraps around; the glider must ignore repeats and never animate backwards across the map. Tests in Task 14.
5. **Basemap absent** — before `tools/build_basemap.sh` has run (or if it fails), the page must still render tracks, stations and trains on the land color, not a blank panel or a JS exception. `/basemap.pmtiles` returns 404 and `map.js` drops the vector source. Tests in Task 13 (server) and checked in Task 15 (browser).

---

## File map

```
pyproject.toml, config.toml, .env.example, package.json, README.md
src/wmata_board/
  __init__.py      __version__
  __main__.py      CLI: --config, --fixtures, --host, --port, --log-level
  lines.py         line codes, GTFS route_id → code
  config.py        load + validate config.toml; API key from env / .env
  wmata.py         WmataClient + WmataError
  fixtures.py      FixtureClient (same interface, reads tests/fixtures-style dir)
  predictions.py   GetPrediction → Train/Platform (pure)
  service.py       jStationInfo/jStationTimes → StationData, ServiceStatus (pure)
  incidents.py     Incidents → Alert (pure)
  positions.py     GTFS-RT → PositionsSnapshot (pure)
  network.py       GTFS static zip → lines/stations (pure) + NetworkCache
  state.py         FeedState
  poller.py        Feed, Poller
  feeds.py         build_feeds(): wires client → Feed objects
  board.py         build_board() → /api/board dict (pure)
  app.py           create_app(): routes, static, basemap range serving
web/
  index.html board.css board.js       wall
  phone.html phone.css phone.js       phone
  format.js render.js track.js        pure helpers (node-tested)
  map.js style.json                   map
  fonts/ vendor/
tests/  test_*.py, helpers.py, fixtures/, js/*.test.js
tools/build_basemap.sh, tools/record_fixtures.py
deploy/wmata-board.service
```

Fixtures already in `tests/fixtures/` (recorded live 2026-10-20): `predictions_K01.json` (incl. `NewCrlton`), `predictions_K01_late.json` (incl. `LastTrain`), `incidents_empty.json`, `station_info_K01.json`, `station_times_K01.json`, `positions/vp_*.pb` (13 GTFS-RT snapshots, 5 s apart). Task 5 adds `incidents.json`; Task 12 adds `network.json`.

---

# Milestone 1 — Backend

### Task 1: Scaffold, line codes, config

**Files:**
- Create: `pyproject.toml`, `config.toml`, `.env.example`, `src/wmata_board/__init__.py`, `src/wmata_board/lines.py`, `src/wmata_board/config.py`, `tests/test_config.py`, `tests/conftest.py`
- Modify: `.gitignore` (add `*.egg-info/`, `node_modules/`)

**Interfaces:**
- Produces: `wmata_board.lines.LINE_CODES: tuple[str, ...]`, `ROUTE_LINES: dict[str, str]`; `wmata_board.config.load_config(path: Path, *, environ: Mapping[str,str] | None = None) -> Config`, `ConfigError`, dataclasses `Config(board, platforms, polling, map, server, api_key)`, `BoardConfig(stations, lines, rows_per_direction, timezone, .station)`, `PollingConfig(arrivals, incidents, positions, idle_after)`, `MapConfig(bbox, labels, places, landmarks)`, `Place(name, lat, lon)`, `Landmark(name, lat, lon, style)`, `ServerConfig(host, port)`; `PROJECT_ROOT` lives in `app.py` (Task 7), not here.

- [ ] **Step 1: Create the scaffold**

`pyproject.toml`:
```toml
[project]
name = "wmata-board"
version = "0.1.0"
description = "Court House departure board: live arrivals, alerts and a train map for the wall kiosk"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "gtfs-realtime-bindings>=1.0",
    "tzdata>=2024.1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

`config.toml` — exactly the spec's block, with comments:
```toml
# wmata-board configuration. Edit and restart:
#   systemctl --user restart wmata-board
# The API key is NOT here: it comes from WMATA_API_KEY in the environment
# (~/wmata-board.env on the Pi) or a gitignored .env next to this file.

[board]
stations = ["K01"]
lines = ["OR", "SV"]          # omit to use every line the station serves
rows_per_direction = 3
timezone = "America/New_York"

[stations.K01.platforms]      # WMATA "Group" -> label; K01: 1 = eastbound, 2 = westbound
1 = "To Washington · New Carrollton"
2 = "To Vienna · Ashburn"

[polling]                      # seconds
arrivals = 20
incidents = 60
positions = 5
idle_after = 90                # a feed is polled only this long after someone last asked

[map]
bbox = [-77.122, 38.844, -76.978, 38.966]   # west, south, east, north
labels = ["K04", "K02", "C05", "C04", "C01", "D03", "B03", "A03", "C07", "F05", "B05"]
places = [["GEORGETOWN", 38.9085, -77.0665], ["THE MALL", 38.8873, -77.0405], ["ARLINGTON", 38.8705, -77.106], ["WASHINGTON", 38.9335, -77.096]]

[[map.landmarks]]
name = "Children's National"
lat = 38.92711
lon = -77.01417
style = "hospital"

[server]
host = "127.0.0.1"
port = 8766
```

`.env.example`:
```
# Copy to .env (gitignored) for local runs against the live API.
WMATA_API_KEY=your-primary-key-here
```

`src/wmata_board/__init__.py`:
```python
"""Court House departure board."""

__version__ = "0.1.0"
```

`src/wmata_board/lines.py`:
```python
"""The six Metrorail lines, in the two vocabularies WMATA uses.

The JSON APIs say "OR"; the GTFS feeds say "ORANGE". Everything we serve
uses the two-letter codes, so GTFS route_ids are mapped here on ingest.
"""

LINE_CODES = ("RD", "OR", "SV", "BL", "GR", "YL")

ROUTE_LINES = {
    "RED": "RD",
    "ORANGE": "OR",
    "SILVER": "SV",
    "BLUE": "BL",
    "GREEN": "GR",
    "YELLOW": "YL",
}

# Lines that run mostly north-south: their shapes are oriented S->N, the rest
# W->E, so lines sharing track run the same way and lane offsets stay on
# consistent sides.
NORTH_SOUTH = frozenset({"GR", "YL"})
```

`tests/conftest.py`:
```python
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).parents[1]


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
```

Append to `.gitignore`: `*.egg-info/` and `node_modules/`.

Create the venv and install: `python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing config tests**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wmata_board.config'`

- [ ] **Step 4: Implement `src/wmata_board/config.py`**

```python
"""Typed configuration loaded from config.toml.

Nothing else in the package reads the TOML file or the environment -- it all
comes through here. The one secret, the WMATA API key, comes from the
environment (systemd's EnvironmentFile on the Pi) or a gitignored `.env` next
to the config file. It never lives in config.toml and never appears in a repr.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .lines import LINE_CODES

_STATION_RE = re.compile(r"^[A-Z]\d{2}$")
API_KEY_VAR = "WMATA_API_KEY"


class ConfigError(ValueError):
    """Raised when the config file is missing a field or holds a bad value."""


@dataclass(frozen=True, slots=True)
class BoardConfig:
    stations: tuple[str, ...] = ("K01",)
    lines: tuple[str, ...] | None = None   # None: every line the station serves
    rows_per_direction: int = 3
    timezone: str = "America/New_York"

    @property
    def station(self) -> str:
        """The station the board shows. The list exists for later layouts."""
        return self.stations[0]


@dataclass(frozen=True, slots=True)
class PollingConfig:
    arrivals: float = 20.0
    incidents: float = 60.0
    positions: float = 5.0
    idle_after: float = 90.0


@dataclass(frozen=True, slots=True)
class Place:
    name: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Landmark:
    name: str
    lat: float
    lon: float
    style: str = "hospital"


@dataclass(frozen=True, slots=True)
class MapConfig:
    bbox: tuple[float, float, float, float] = (-77.122, 38.844, -76.978, 38.966)
    labels: tuple[str, ...] = ()
    places: tuple[Place, ...] = ()
    landmarks: tuple[Landmark, ...] = ()


@dataclass(frozen=True, slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8766


@dataclass(frozen=True)
class Config:
    board: BoardConfig
    platforms: Mapping[str, Mapping[str, str]]
    polling: PollingConfig
    map: MapConfig
    server: ServerConfig
    api_key: str | None = field(default=None, repr=False)


def _number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where} must be a number, got {value!r}")
    return float(value)


def _table(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{name}] must be a table")
    return value


def _board(t: Mapping[str, Any]) -> BoardConfig:
    stations = t.get("stations", ["K01"])
    if not isinstance(stations, list) or not stations:
        raise ConfigError("[board].stations must be a non-empty list")
    codes = tuple(str(s).strip().upper() for s in stations)
    for code in codes:
        if not _STATION_RE.match(code):
            raise ConfigError(f"[board].stations: {code!r} is not a station code like 'K01'")

    lines = t.get("lines")
    if lines is not None:
        if not isinstance(lines, list) or not lines:
            raise ConfigError("[board].lines must be a non-empty list (or omitted)")
        lines = tuple(str(x).strip().upper() for x in lines)
        bad = [x for x in lines if x not in LINE_CODES]
        if bad:
            raise ConfigError(
                f"[board].lines: unknown line(s) {', '.join(bad)} (known: {', '.join(LINE_CODES)})")

    rows = t.get("rows_per_direction", 3)
    if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 6:
        raise ConfigError(f"[board].rows_per_direction must be an integer 1-6, got {rows!r}")

    tz = t.get("timezone", "America/New_York")
    try:
        ZoneInfo(str(tz))
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"[board].timezone: unknown timezone {tz!r}") from None

    return BoardConfig(codes, lines, rows, str(tz))


def _platforms(t: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for code, section in t.items():
        if not isinstance(section, Mapping):
            raise ConfigError(f"[stations.{code}] must be a table")
        labels = section.get("platforms", {})
        if not isinstance(labels, Mapping):
            raise ConfigError(f"[stations.{code}.platforms] must be a table")
        out[str(code).upper()] = {str(k): str(v) for k, v in labels.items()}
    return out


def _polling(t: Mapping[str, Any]) -> PollingConfig:
    values = {}
    for name in ("arrivals", "incidents", "positions", "idle_after"):
        if name in t:
            v = _number(t[name], f"[polling].{name}")
            if v <= 0:
                raise ConfigError(f"[polling].{name} must be > 0")
            values[name] = v
    return PollingConfig(**values)


def _map(t: Mapping[str, Any]) -> MapConfig:
    bbox = t.get("bbox", list(MapConfig.bbox))
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ConfigError("[map].bbox must be [west, south, east, north]")
    west, south, east, north = (_number(v, "[map].bbox") for v in bbox)
    if not (west < east and south < north):
        raise ConfigError("[map].bbox must be [west, south, east, north] with west < east, south < north")

    labels = t.get("labels", [])
    if not isinstance(labels, list):
        raise ConfigError("[map].labels must be a list of station codes")

    places = []
    for item in t.get("places", []):
        if not isinstance(item, list) or len(item) != 3:
            raise ConfigError(f"[map].places entries must be [name, lat, lon], got {item!r}")
        places.append(Place(str(item[0]), _number(item[1], "[map].places"), _number(item[2], "[map].places")))

    landmarks = []
    for item in t.get("landmarks", []):
        if not isinstance(item, Mapping) or not {"name", "lat", "lon"} <= set(item):
            raise ConfigError("[[map.landmarks]] entries need name, lat and lon")
        landmarks.append(Landmark(str(item["name"]), _number(item["lat"], "[[map.landmarks]].lat"),
                                  _number(item["lon"], "[[map.landmarks]].lon"),
                                  str(item.get("style", "hospital"))))

    return MapConfig((west, south, east, north), tuple(str(x).upper() for x in labels),
                     tuple(places), tuple(landmarks))


def _server(t: Mapping[str, Any]) -> ServerConfig:
    host = str(t.get("host", "127.0.0.1"))
    port = t.get("port", 8766)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError(f"[server].port must be 1-65535, got {port!r}")
    return ServerConfig(host, port)


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; comments, blank lines, `export ` and quotes tolerated."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _api_key(environ: Mapping[str, str], dotenv: Path) -> str | None:
    key = environ.get(API_KEY_VAR, "").strip()
    if not key:
        key = read_dotenv(dotenv).get(API_KEY_VAR, "").strip()
    return key or None


def load_config(path: Path, *, environ: Mapping[str, str] | None = None) -> Config:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: {exc}") from None

    return Config(
        board=_board(_table(raw, "board")),
        platforms=_platforms(_table(raw, "stations")),
        polling=_polling(_table(raw, "polling")),
        map=_map(_table(raw, "map")),
        server=_server(_table(raw, "server")),
        api_key=_api_key(os.environ if environ is None else environ, path.parent / ".env"),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: all PASS. (The `'[board\n'` case's message names `config.toml` because the error is prefixed with `path.name`.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml config.toml .env.example .gitignore src tests/conftest.py tests/test_config.py tests/fixtures
git commit -m "Scaffold wmata_board package with validated TOML config"
```

---

### Task 2: WMATA client and fixture client

**Files:**
- Create: `src/wmata_board/wmata.py`, `src/wmata_board/fixtures.py`, `tests/test_wmata.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `WmataError(kind: str, message: str)` with `.kind` in `{"no_key","api_key","rate_limited","http","network","parse"}` and `.message`.
  - `WmataClient(api_key: str | None, *, base_url=BASE_URL, timeout=8.0, transport: httpx.AsyncBaseTransport | None = None)` with async methods `predictions(stations: Sequence[str]) -> Any`, `incidents() -> Any`, `station_info(code) -> Any`, `station_times(code) -> Any`, `vehicle_positions() -> bytes`, `gtfs_static() -> bytes`, `aclose()`.
  - `FixtureClient(root: Path)` with the same methods; reads `predictions_<codes>.json`, `incidents.json`, `station_info_<code>.json`, `station_times_<code>.json`, cycles `positions/*.pb` in name order; `gtfs_static()` raises `WmataError("http", ...)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_wmata.py`:
```python
import json

import httpx
import pytest

from wmata_board.fixtures import FixtureClient
from wmata_board.wmata import WmataClient, WmataError

KEY = "test-key-123"


def client_for(handler) -> WmataClient:
    return WmataClient(KEY, base_url="https://api.test", transport=httpx.MockTransport(handler))


async def test_sends_header_and_builds_prediction_path():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("api_key")
        return httpx.Response(200, json={"Trains": []})

    assert await client_for(handler).predictions(["K01", "C05"]) == {"Trains": []}
    assert seen["url"] == "https://api.test/StationPrediction.svc/json/GetPrediction/K01,C05"
    assert seen["key"] == KEY


async def test_station_endpoints_use_station_code_param():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={})

    c = client_for(handler)
    await c.station_info("K01")
    await c.station_times("K01")
    await c.incidents()
    assert urls == [
        "https://api.test/Rail.svc/json/jStationInfo?StationCode=K01",
        "https://api.test/Rail.svc/json/jStationTimes?StationCode=K01",
        "https://api.test/Incidents.svc/json/Incidents",
    ]


async def test_binary_endpoints_return_bytes():
    def handler(request):
        return httpx.Response(200, content=b"\x0a\x00")

    c = client_for(handler)
    assert await c.vehicle_positions() == b"\x0a\x00"
    assert await c.gtfs_static() == b"\x0a\x00"


@pytest.mark.parametrize("status, kind", [(401, "api_key"), (403, "api_key"), (429, "rate_limited"),
                                          (400, "http"), (500, "http"), (503, "http")])
async def test_status_codes_map_to_kinds(status, kind):
    c = client_for(lambda r: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(WmataError) as err:
        await c.incidents()
    assert err.value.kind == kind
    assert KEY not in err.value.message


async def test_network_failure_is_network_kind():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(WmataError) as err:
        await client_for(handler).incidents()
    assert err.value.kind == "network"


async def test_timeout_is_network_kind():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(WmataError) as err:
        await client_for(handler).incidents()
    assert err.value.kind == "network"


async def test_bad_json_is_parse_kind():
    c = client_for(lambda r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(WmataError) as err:
        await c.incidents()
    assert err.value.kind == "parse"


async def test_no_key_never_calls_out():
    def handler(request):
        raise AssertionError("must not be called")

    c = WmataClient(None, transport=httpx.MockTransport(handler))
    with pytest.raises(WmataError) as err:
        await c.predictions(["K01"])
    assert err.value.kind == "no_key"


async def test_fixture_client_reads_files(fixtures):
    c = FixtureClient(fixtures)
    data = await c.predictions(["K01"])
    assert data == json.loads((fixtures / "predictions_K01.json").read_text(encoding="utf-8"))
    assert (await c.station_info("K01"))["Name"] == "Court House"
    assert "StationTimes" in await c.station_times("K01")


async def test_fixture_client_cycles_positions(fixtures):
    c = FixtureClient(fixtures)
    files = sorted((fixtures / "positions").glob("*.pb"))
    got = [await c.vehicle_positions() for _ in range(len(files) + 1)]
    assert got[0] == files[0].read_bytes()
    assert got[1] == files[1].read_bytes()
    assert got[-1] == files[0].read_bytes()


async def test_fixture_client_missing_file_is_wmata_error(tmp_path):
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).incidents()
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).vehicle_positions()
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).gtfs_static()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_wmata.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'wmata_board.fixtures'`

- [ ] **Step 3: Implement `src/wmata_board/wmata.py`**

```python
"""The one place that talks to api.wmata.com.

Every failure comes out as a WmataError with a short `kind` the board can act
on (an expired key reads differently from a network blip). Messages name the
endpoint, never the key.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

BASE_URL = "https://api.wmata.com"
TIMEOUT_S = 8.0
STATIC_TIMEOUT_S = 60.0  # the GTFS static zip is ~3 MB


class WmataError(Exception):
    """kind: no_key | api_key | rate_limited | http | network | parse"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class WmataClient:
    def __init__(self, api_key: str | None, *, base_url: str = BASE_URL,
                 timeout: float = TIMEOUT_S,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._has_key = bool(api_key)
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport,
            headers={"api_key": api_key} if api_key else {},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict | None = None,
                   timeout: float | None = None) -> httpx.Response:
        if not self._has_key:
            raise WmataError("no_key", "No WMATA API key configured")
        try:
            if timeout is None:
                resp = await self._http.get(path, params=params)
            else:
                resp = await self._http.get(path, params=params, timeout=timeout)
        except httpx.TimeoutException:
            raise WmataError("network", f"timed out fetching {path}") from None
        except httpx.HTTPError as exc:
            raise WmataError("network", f"{type(exc).__name__} fetching {path}") from None
        if resp.status_code in (401, 403):
            raise WmataError("api_key", f"WMATA rejected the API key (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise WmataError("rate_limited", "WMATA rate limit hit (HTTP 429)")
        if resp.status_code >= 400:
            raise WmataError("http", f"HTTP {resp.status_code} from {path}")
        return resp

    async def _json(self, path: str, params: dict | None = None) -> Any:
        resp = await self._get(path, params)
        try:
            return resp.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise WmataError("parse", f"bad JSON from {path}") from None

    async def predictions(self, stations: Sequence[str]) -> Any:
        return await self._json(f"/StationPrediction.svc/json/GetPrediction/{','.join(stations)}")

    async def incidents(self) -> Any:
        return await self._json("/Incidents.svc/json/Incidents")

    async def station_info(self, code: str) -> Any:
        return await self._json("/Rail.svc/json/jStationInfo", {"StationCode": code})

    async def station_times(self, code: str) -> Any:
        return await self._json("/Rail.svc/json/jStationTimes", {"StationCode": code})

    async def vehicle_positions(self) -> bytes:
        return (await self._get("/gtfs/rail-gtfsrt-vehiclepositions.pb")).content

    async def gtfs_static(self) -> bytes:
        return (await self._get("/gtfs/rail-gtfs-static.zip", timeout=STATIC_TIMEOUT_S)).content
```

- [ ] **Step 4: Implement `src/wmata_board/fixtures.py`**

```python
"""A stand-in for WmataClient that replays recorded responses (`--fixtures`).

Lets the whole board run on a laptop with no key and no network. Position
snapshots are replayed in order, one per call, wrapping at the end -- they
were recorded 5 s apart, the same as the positions cadence.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .wmata import WmataError


class FixtureClient:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._snapshots = sorted((self._root / "positions").glob("*.pb"))
        self._next = 0

    def _load(self, name: str) -> Any:
        try:
            return json.loads((self._root / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise WmataError("http", f"fixture {name} missing") from None

    async def predictions(self, stations: Sequence[str]) -> Any:
        return self._load(f"predictions_{','.join(stations)}.json")

    async def incidents(self) -> Any:
        return self._load("incidents.json")

    async def station_info(self, code: str) -> Any:
        return self._load(f"station_info_{code}.json")

    async def station_times(self, code: str) -> Any:
        return self._load(f"station_times_{code}.json")

    async def vehicle_positions(self) -> bytes:
        if not self._snapshots:
            raise WmataError("http", "no position fixtures")
        data = self._snapshots[self._next % len(self._snapshots)].read_bytes()
        self._next += 1
        return data

    async def gtfs_static(self) -> bytes:
        raise WmataError("http", "fixtures mode has no GTFS static zip (uses network.json)")

    async def aclose(self) -> None:
        pass
```

- [ ] **Step 5: Run tests** — `.venv/Scripts/python -m pytest tests/test_wmata.py -q` → `test_fixture_client_missing_file_is_wmata_error` passes; everything PASS. (`incidents.json` is not needed here: the cycling/reads tests don't touch it.)

- [ ] **Step 6: Commit** — `git add src/wmata_board/wmata.py src/wmata_board/fixtures.py tests/test_wmata.py && git commit -m "WMATA client with typed errors, plus fixture replay client"`

---

### Task 3: Predictions parsing

**Files:**
- Create: `src/wmata_board/predictions.py`, `tests/test_predictions.py`

**Interfaces:**
- Consumes: `WmataError` (Task 2).
- Produces: `Train(station, group, line, cars: int|None, destination, minutes: int|None, display)` with `.as_json() -> {"line","cars","destination","minutes","display"}`; `Platform(group, label, trains: tuple[Train,...])` with `.as_json() -> {"group","label","trains":[...]}`; `parse_predictions(payload, stations: Iterable[str], lines: Iterable[str] | None = None) -> list[Train]`; `platforms_for(trains, station: str, labels: Mapping[str,str], rows: int) -> list[Platform]`; `destination_of(raw) -> str`; `DESTINATION_ALIASES`; `NO_TIME = "—"`.

- [ ] **Step 1: Write failing tests** — `tests/test_predictions.py`:
```python
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
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_predictions.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement `src/wmata_board/predictions.py`**
```python
"""WMATA GetPrediction responses, normalized into what the board shows. Pure."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .wmata import WmataError

# Abbreviations WMATA sends with a null DestinationCode. Extend as new ones
# turn up in the journal ("LastTrain" was seen on 2026-10-20 around midnight).
DESTINATION_ALIASES = {
    "NewCrlton": "New Carrollton",
    "LastTrain": "Last train",
}
_NO_PASSENGER_LINES = {"", "NO", "--"}
_SPECIAL_ORDER = {"BRD": 0, "ARR": 1}
NO_TIME = "—"


@dataclass(frozen=True, slots=True)
class Train:
    station: str
    group: str
    line: str
    cars: int | None
    destination: str
    minutes: int | None
    display: str

    def as_json(self) -> dict:
        return {"line": self.line, "cars": self.cars, "destination": self.destination,
                "minutes": self.minutes, "display": self.display}


@dataclass(frozen=True, slots=True)
class Platform:
    group: str
    label: str
    trains: tuple[Train, ...]

    def as_json(self) -> dict:
        return {"group": self.group, "label": self.label,
                "trains": [t.as_json() for t in self.trains]}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def destination_of(raw: Mapping[str, Any]) -> str:
    name = _text(raw.get("DestinationName"))
    dest = _text(raw.get("Destination"))
    if _text(raw.get("DestinationCode")) and name:
        return name
    for candidate in (name, dest):
        if candidate in DESTINATION_ALIASES:
            return DESTINATION_ALIASES[candidate]
    return dest or name or "Train"


def _minutes(value: Any) -> tuple[int | None, str]:
    m = _text(value).upper()
    if m in _SPECIAL_ORDER:
        return 0, m
    if m.isdigit():
        return int(m), str(int(m))
    return None, NO_TIME


def _is_passenger(raw: Mapping[str, Any]) -> bool:
    if _text(raw.get("Line")).upper() in _NO_PASSENGER_LINES:
        return False
    return not any("ssenger" in _text(raw.get(k)).lower() for k in ("Destination", "DestinationName"))


def parse_predictions(payload: Any, stations: Iterable[str],
                      lines: Iterable[str] | None = None) -> list[Train]:
    trains = payload.get("Trains") if isinstance(payload, Mapping) else None
    if not isinstance(trains, list):
        raise WmataError("parse", "prediction response has no Trains list")
    wanted_stations = set(stations)
    wanted_lines = None if lines is None else set(lines)

    out = []
    for raw in trains:
        if not isinstance(raw, Mapping) or not _is_passenger(raw):
            continue
        station = _text(raw.get("LocationCode"))
        line = _text(raw.get("Line")).upper()
        if station not in wanted_stations or (wanted_lines is not None and line not in wanted_lines):
            continue
        minutes, display = _minutes(raw.get("Min"))
        car = _text(raw.get("Car"))
        out.append(Train(station, _text(raw.get("Group")), line,
                         int(car) if car.isdigit() else None,
                         destination_of(raw), minutes, display))
    return out


def _sort_key(train: Train) -> tuple[int, int]:
    if train.display in _SPECIAL_ORDER:
        return 0, _SPECIAL_ORDER[train.display]
    if train.minutes is not None:
        return 1, train.minutes
    return 2, 0


def _group_key(group: str) -> tuple[int, int, str]:
    return (0, int(group), "") if group.isdigit() else (1, 0, group)


def _default_label(trains: Iterable[Train]) -> str:
    dests = list(dict.fromkeys(t.destination for t in trains))
    return "To " + " · ".join(dests) if dests else "Platform"


def platforms_for(trains: Iterable[Train], station: str, labels: Mapping[str, str],
                  rows: int) -> list[Platform]:
    groups: dict[str, list[Train]] = {g: [] for g in labels}
    for t in trains:
        if t.station == station:
            groups.setdefault(t.group, []).append(t)
    out = []
    for group in sorted(groups, key=_group_key):
        ordered = sorted(groups[group], key=_sort_key)
        out.append(Platform(group, labels.get(group) or _default_label(ordered), tuple(ordered[:rows])))
    return out
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git add src/wmata_board/predictions.py tests/test_predictions.py && git commit -m "Parse and order arrivals, with destination aliases"`

---

### Task 4: Station info and service window

**Files:**
- Create: `src/wmata_board/service.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `WmataError`.
- Produces: `StationData(code, name, lines: tuple[str,...], times: Any)`; `station_data(code, info_payload, times_payload) -> StationData`; `ServiceStatus(first_train: str, last_train: str, in_service: bool, resumes: str | None)` with `.as_json() -> {"first_train","last_train"}`; `service_status(times_payload, station, now: datetime) -> ServiceStatus | None` (`now` tz-aware local); `clock_label(dt) -> "5:19 AM"`.

- [ ] **Step 1: Failing tests** — `tests/test_service.py`:
```python
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
```

- [ ] **Step 2: Run** → FAIL. 

- [ ] **Step 3: Implement `src/wmata_board/service.py`**
```python
"""Station facts from jStationInfo / jStationTimes, and whether the station is
in service right now. Pure.

A service day starts at 04:00: WMATA lists the last trains as clock times, and
"00:20" (or "02:20" on Friday and Saturday nights) belongs to the evening
before. jStationTimes' OpeningTime is not trusted -- Saturday's says 07:10
while its first train is at 06:14 -- so the window is the earliest first train
to the latest last train.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from .wmata import WmataError

SERVICE_DAY_STARTS = time(4, 0)
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True, slots=True)
class StationData:
    code: str
    name: str
    lines: tuple[str, ...]
    times: Any


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    first_train: str
    last_train: str
    in_service: bool
    resumes: str | None

    def as_json(self) -> dict:
        return {"first_train": self.first_train, "last_train": self.last_train}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def station_data(code: str, info: Any, times: Any) -> StationData:
    info = info if isinstance(info, Mapping) else {}
    lines = tuple(x for k in ("LineCode1", "LineCode2", "LineCode3", "LineCode4")
                  if (x := _text(info.get(k)).upper()))
    return StationData(code, _text(info.get("Name")) or code, lines, times)


def clock_label(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def _entry(payload: Any, station: str) -> Mapping[str, Any]:
    entries = payload.get("StationTimes") if isinstance(payload, Mapping) else None
    for e in entries or []:
        if isinstance(e, Mapping) and e.get("Code") == station:
            return e
    raise WmataError("parse", f"no station times for {station}")


def _window(entry: Mapping[str, Any], day: date, now: datetime) -> tuple[datetime, datetime] | None:
    sched = entry.get(_DAYS[day.weekday()])
    if not isinstance(sched, Mapping):
        return None

    def at(hhmm: str) -> datetime:
        t = time.fromisoformat(hhmm)
        d = day + timedelta(days=1) if t < SERVICE_DAY_STARTS else day
        return datetime.combine(d, t, now.tzinfo)

    def times(key: str) -> list[datetime]:
        out = []
        for item in sched.get(key) or []:
            try:
                out.append(at(_text(item.get("Time"))))
            except (AttributeError, ValueError):
                continue
        return out

    firsts, lasts = times("FirstTrains"), times("LastTrains")
    if not firsts or not lasts:
        return None
    return min(firsts), max(lasts)


def service_status(times_payload: Any, station: str, now: datetime) -> ServiceStatus | None:
    entry = _entry(times_payload, station)
    service_day = (now - timedelta(hours=SERVICE_DAY_STARTS.hour)).date()
    window = _window(entry, service_day, now)
    if window is None:
        return None
    first, last = window
    if first <= now <= last:
        return ServiceStatus(clock_label(first), clock_label(last), True, None)
    if now < first:
        resumes: datetime | None = first
    else:
        nxt = _window(entry, service_day + timedelta(days=1), now)
        resumes = nxt[0] if nxt else None
    return ServiceStatus(clock_label(first), clock_label(last), False,
                         clock_label(resumes) if resumes else None)
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `git commit -am`-style: `git add src/wmata_board/service.py tests/test_service.py && git commit -m "Station info and after-midnight-aware service window"`

---

### Task 5: Incidents

**Files:**
- Create: `src/wmata_board/incidents.py`, `tests/test_incidents.py`, `tests/fixtures/incidents.json`

**Interfaces:**
- Produces: `Alert(id, lines: tuple[str,...], text, updated)` with `.as_json() -> {"id","lines","text","updated"}`; `affected_lines(s: str|None) -> tuple[str,...]`; `parse_incidents(payload) -> list[Alert]` (all lines); `alerts_for(alerts, lines: Iterable[str] | None) -> list[Alert]`.

- [ ] **Step 1: Create the sample fixture** `tests/fixtures/incidents.json` (shape per WMATA docs; text invented, used by fixtures mode to show the banner):
```json
{"Incidents": [
  {"DateUpdated": "2026-10-20T21:58:12", "DelaySeverity": null,
   "Description": "Orange/Silver Line: Trains operating every 15 minutes between Ballston and Stadium-Armory due to track maintenance.",
   "EmergencyText": null, "EndLocationFullName": null, "IncidentID": "A1B2C3D4-0000-4000-8000-000000000001",
   "IncidentType": "Alert", "LinesAffected": "OR; SV;", "PassengerDelay": 0, "StartLocationFullName": null},
  {"DateUpdated": "2026-10-20T20:11:40", "DelaySeverity": null,
   "Description": "Red Line: Expect residual delays to Glenmont due to an earlier signal problem outside Forest Glen.",
   "EmergencyText": null, "EndLocationFullName": null, "IncidentID": "A1B2C3D4-0000-4000-8000-000000000002",
   "IncidentType": "Delay", "LinesAffected": "RD;", "PassengerDelay": 0, "StartLocationFullName": null},
  {"DateUpdated": "2026-10-20T19:02:00", "DelaySeverity": null,
   "Description": "Blue/Orange/Silver Line: Single tracking between Foggy Bottom and Smithsonian.",
   "EmergencyText": null, "EndLocationFullName": null, "IncidentID": "A1B2C3D4-0000-4000-8000-000000000003",
   "IncidentType": "Alert", "LinesAffected": "BL;OR;SV;", "PassengerDelay": 0, "StartLocationFullName": null}
]}
```

- [ ] **Step 2: Failing tests** — `tests/test_incidents.py`:
```python
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
```

- [ ] **Step 3: Run** → FAIL. **Step 4: Implement `src/wmata_board/incidents.py`**
```python
"""Rail incidents, reduced to alerts for the lines we care about. Pure."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .wmata import WmataError

_SPLIT = re.compile(r";\s?")


@dataclass(frozen=True, slots=True)
class Alert:
    id: str
    lines: tuple[str, ...]
    text: str
    updated: str

    def as_json(self) -> dict:
        return {"id": self.id, "lines": list(self.lines), "text": self.text, "updated": self.updated}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def affected_lines(s: str | None) -> tuple[str, ...]:
    parts = (p.strip().upper() for p in _SPLIT.split(s or ""))
    return tuple(dict.fromkeys(p for p in parts if p))


def parse_incidents(payload: Any) -> list[Alert]:
    items = payload.get("Incidents") if isinstance(payload, Mapping) else None
    if not isinstance(items, list):
        raise WmataError("parse", "incident response has no Incidents list")
    out = []
    for raw in items:
        if not isinstance(raw, Mapping):
            continue
        text = _text(raw.get("Description"))
        if not text:
            continue
        out.append(Alert(_text(raw.get("IncidentID")) or text, affected_lines(raw.get("LinesAffected")),
                         text, _text(raw.get("DateUpdated"))))
    return out


def alerts_for(alerts: Iterable[Alert], lines: Iterable[str] | None) -> list[Alert]:
    if lines is None:
        return list(alerts)
    wanted = set(lines)
    return [a for a in alerts if wanted.intersection(a.lines)]
```

- [ ] **Step 5: Run** → PASS. **Step 6: Commit** `git add src/wmata_board/incidents.py tests/test_incidents.py tests/fixtures/incidents.json && git commit -m "Parse rail incidents and filter to station lines"`

---

### Task 6: Feed state and poller

**Files:**
- Create: `src/wmata_board/state.py`, `src/wmata_board/poller.py`, `tests/test_poller.py`

**Interfaces:**
- Consumes: `WmataError`.
- Produces:
  - `FeedState` (mutable dataclass): `value`, `fetched_at: float|None` (monotonic), `fetched_wall: datetime|None` (UTC), `error: str|None`, `error_kind: str|None`; `age(now) -> float|None`; `freshness(now, stale_after) -> {"age_s": int|None, "stale": bool, "error": str|None}`.
  - `Feed(name, fetch: Callable[[], Awaitable[Any]], cadence: float, *, gated=True, idle_after=90.0, max_backoff=300.0, clock=time.monotonic)`: `.state`, `.next_at`, `.want() -> bool` (True if it was idle), `.wanted() -> bool`, `.due() -> bool`, `async step() -> float` (delay), `async wait_for_update(timeout) -> bool`, `async run()`.
  - `Poller(feeds: Mapping[str, Feed])`: `.feeds`, `__getitem__`, `start()`, `async stop()`.

- [ ] **Step 1: Failing tests** — `tests/test_poller.py`:
```python
import asyncio

import pytest

from wmata_board.poller import Feed, Poller
from wmata_board.state import FeedState
from wmata_board.wmata import WmataError


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(fetch, cadence=20.0, **kw):
    clock = Clock()
    return Feed("arrivals", fetch, cadence, clock=clock, **kw), clock


def test_freshness():
    s = FeedState()
    assert s.age(5.0) is None
    assert s.freshness(5.0, 60) == {"age_s": None, "stale": False, "error": None}
    s.fetched_at, s.error_kind = 0.0, "network"
    assert s.freshness(61.4, 60) == {"age_s": 61, "stale": True, "error": "network"}
    assert s.freshness(30.0, 60)["stale"] is False


async def test_success_stores_value_and_schedules_cadence():
    async def fetch():
        return 42

    feed, clock = make(fetch)
    assert await feed.step() == 20.0
    assert feed.state.value == 42
    assert feed.state.fetched_at == clock.t
    assert feed.state.fetched_wall is not None
    assert feed.state.error is None
    assert feed.next_at == clock.t + 20.0


async def test_backoff_doubles_and_caps_then_resets():
    outcome = {"fail": True}

    async def fetch():
        if outcome["fail"]:
            raise WmataError("network", "down")
        return "ok"

    feed, _ = make(fetch)
    delays = [await feed.step() for _ in range(5)]
    assert delays == [40.0, 80.0, 160.0, 300.0, 300.0]
    assert feed.state.error == "down" and feed.state.error_kind == "network"
    outcome["fail"] = False
    assert await feed.step() == 20.0
    assert feed.state.error is None and feed.state.error_kind is None


async def test_failure_keeps_last_good_value():
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        if calls["n"] > 1:
            raise WmataError("rate_limited", "429")
        return "good"

    feed, _ = make(fetch)
    await feed.step()
    await feed.step()
    assert feed.state.value == "good"
    assert feed.state.error_kind == "rate_limited"


async def test_unexpected_exception_never_escapes():
    async def fetch():
        raise RuntimeError("bug")

    feed, _ = make(fetch)
    assert await feed.step() == 40.0
    assert feed.state.error_kind == "internal"


async def test_long_cadence_backoff_is_capped_below_cadence():
    async def fetch():
        raise WmataError("network", "down")

    feed, _ = make(fetch, cadence=86400.0)
    assert await feed.step() == 300.0


def test_demand_gating():
    async def fetch():
        return 1

    feed, clock = make(fetch, idle_after=90.0)
    assert not feed.wanted()
    assert feed.want() is True           # was idle
    assert feed.wanted()
    clock.t += 30
    assert feed.want() is False          # still wanted
    clock.t += 89
    assert feed.wanted()
    clock.t += 2
    assert not feed.wanted()


def test_ungated_always_wanted():
    async def fetch():
        return 1

    feed, _ = make(fetch, gated=False)
    assert feed.wanted()


async def test_due():
    async def fetch():
        return 1

    feed, clock = make(fetch)
    assert feed.due()
    await feed.step()
    assert not feed.due()
    clock.t += 20
    assert feed.due()


async def test_wait_for_update():
    async def fetch():
        return 1

    feed, _ = make(fetch)
    waiter = asyncio.create_task(feed.wait_for_update(1.0))
    await asyncio.sleep(0)
    await feed.step()
    assert await waiter is True
    assert await feed.wait_for_update(0.01) is False


async def test_run_loop_idles_until_wanted_then_polls():
    calls = []

    async def fetch():
        calls.append(1)
        return len(calls)

    feed = Feed("p", fetch, 0.02, idle_after=60.0)   # real clock
    poller = Poller({"p": feed})
    poller.start()
    await asyncio.sleep(0.05)
    assert calls == []                  # nobody asked
    feed.want()
    await asyncio.sleep(0.11)
    assert len(calls) >= 3
    assert poller["p"] is feed
    await poller.stop()
    n = len(calls)
    await asyncio.sleep(0.05)
    assert len(calls) == n              # stopped
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement `src/wmata_board/state.py`**
```python
"""Last-known value of one feed, when it was fetched, and the last error."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class FeedState:
    value: Any = None
    fetched_at: float | None = None        # monotonic clock
    fetched_wall: datetime | None = None   # UTC, for display
    error: str | None = None
    error_kind: str | None = None

    def age(self, now: float) -> float | None:
        return None if self.fetched_at is None else max(0.0, now - self.fetched_at)

    def freshness(self, now: float, stale_after: float) -> dict:
        age = self.age(now)
        return {"age_s": None if age is None else int(age),
                "stale": age is not None and age > stale_after,
                "error": self.error_kind}
```

`src/wmata_board/poller.py`:
```python
"""One asyncio task per feed: cadence, demand gating, backoff.

A gated feed is fetched only while someone has asked for it in the last
`idle_after` seconds -- with the wall on skyview and no phone open, WMATA is
not called at all. `step()` is the whole fetch-and-record cycle and never
raises, so `run()` can loop forever; tests drive `step()` with a fake clock.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from .state import FeedState
from .wmata import WmataError

log = logging.getLogger("wmata_board.poller")


class Feed:
    def __init__(self, name: str, fetch: Callable[[], Awaitable[Any]], cadence: float, *,
                 gated: bool = True, idle_after: float = 90.0, max_backoff: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self.cadence = cadence
        self.state = FeedState()
        self.next_at = -math.inf
        self._fetch = fetch
        self._gated = gated
        self._idle_after = idle_after
        self._max_backoff = max_backoff
        self._clock = clock
        self._failures = 0
        self._wanted_until = -math.inf
        self._wake = asyncio.Event()
        self._updated = asyncio.Event()

    def wanted(self) -> bool:
        return not self._gated or self._clock() < self._wanted_until

    def want(self) -> bool:
        """Someone is looking. Returns True if the feed had gone idle."""
        was_idle = not self.wanted()
        self._wanted_until = self._clock() + self._idle_after
        self._wake.set()
        return was_idle

    def due(self) -> bool:
        return self._clock() >= self.next_at

    async def step(self) -> float:
        try:
            value = await self._fetch()
        except WmataError as exc:
            delay = self._failed(exc.kind, exc.message)
            log.warning("%s: %s (retry in %.0fs)", self.name, exc.message, delay)
        except Exception as exc:  # a parsing bug must not kill the feed
            delay = self._failed("internal", f"{type(exc).__name__}: {exc}")
            log.exception("%s: unexpected error (retry in %.0fs)", self.name, delay)
        else:
            if self._failures:
                log.info("%s: recovered", self.name)
            self._failures = 0
            self.state.value = value
            self.state.fetched_at = self._clock()
            self.state.fetched_wall = datetime.now(UTC)
            self.state.error = self.state.error_kind = None
            delay = self.cadence
        self.next_at = self._clock() + delay
        updated, self._updated = self._updated, asyncio.Event()
        updated.set()
        return delay

    def _failed(self, kind: str, message: str) -> float:
        self._failures += 1
        self.state.error, self.state.error_kind = message, kind
        return min(self.cadence * 2 ** self._failures, self._max_backoff)

    async def wait_for_update(self, timeout: float) -> bool:
        event = self._updated
        try:
            await asyncio.wait_for(event.wait(), timeout)
            return True
        except TimeoutError:
            return False

    async def run(self) -> None:
        while True:
            if not self.wanted():
                self._wake.clear()
                await self._wake.wait()
                continue
            wait = self.next_at - self._clock()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            await self.step()


class Poller:
    def __init__(self, feeds: Mapping[str, Feed]) -> None:
        self.feeds = dict(feeds)
        self._tasks: list[asyncio.Task] = []

    def __getitem__(self, name: str) -> Feed:
        return self.feeds[name]

    def start(self) -> None:
        self._tasks = [asyncio.create_task(f.run(), name=f"feed:{n}") for n, f in self.feeds.items()]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
```
Note: `asyncio.TimeoutError` is an alias of builtin `TimeoutError` on 3.11+, so the except catches `wait_for` timeouts.

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest tests/test_poller.py -q` → PASS. **Step 5: Commit** `git add src/wmata_board/state.py src/wmata_board/poller.py tests/test_poller.py && git commit -m "Feed poller with demand gating and capped backoff"`

---

### Task 7: Board assembly, feeds wiring, app, CLI (fixtures mode)

**Files:**
- Create: `src/wmata_board/board.py`, `src/wmata_board/feeds.py`, `src/wmata_board/app.py`, `src/wmata_board/__main__.py`, `tests/test_board.py`, `tests/test_app.py`, `tests/helpers.py`
- Create placeholder `web/index.html` (`<!doctype html><title>Court House</title>`) so `/` resolves; Task 8 replaces it.

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces:
  - `board.build_board(*, config, arrivals: FeedState, incidents: FeedState, station: FeedState, now: float, now_local: datetime, version: str) -> dict` (shape below); constants `STALE_AFTER_S = 60`, `INCIDENTS_STALE_AFTER_S = 180`, `UNAVAILABLE_AFTER_S = 600`; notice strings `NOTICE_NO_KEY = "No WMATA API key configured"`, `NOTICE_BAD_KEY = "WMATA rejected the API key"`, `NOTICE_LOADING = "Loading arrivals…"`, `NOTICE_UNAVAILABLE = "Live arrivals unavailable"`.
  - `feeds.build_feeds(config, client, *, network_loader=None, clock=time.monotonic) -> dict[str, Feed]` with keys `arrivals, incidents, station` (and `positions`, `network` added in Tasks 11–12).
  - `app.create_app(config, client, *, feeds=None, version=__version__, fresh_wait_s=3.0, start_polling=True, data_dir=DATA_DIR, clock=time.monotonic) -> FastAPI`; `app.state.feeds`; `PROJECT_ROOT`, `WEB_DIR`, `DATA_DIR`.
  - `/api/board` JSON:
    ```
    {station: {code, name}, timezone, generated_at, version,
     platforms: [{group, label, trains: [{line, cars, destination, minutes, display}]}],
     notice: str | null, alerts: [{id, lines, text, updated}],
     service: {first_train, last_train} | null,
     freshness: {arrivals: {age_s, stale, error}, incidents: {age_s, stale, error}}}
    ```
  - `/healthz` → `{ok: true, version, api_key: bool, feeds: {name: {age_s, error}}}`.

- [ ] **Step 1: Test helpers** — `tests/helpers.py`:
```python
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
```

- [ ] **Step 2: Failing board tests** — `tests/test_board.py`:
```python
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
```

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_board.py -q` → FAIL.

- [ ] **Step 4: Implement `src/wmata_board/board.py`**
```python
"""Assemble the /api/board payload from feed states. Pure.

The server decides what the arrivals panel should say (`notice`) so the wall
and phone pages stay dumb: when `notice` is set they show it instead of rows.
"""

from __future__ import annotations

from datetime import datetime

from .config import Config
from .incidents import alerts_for
from .predictions import platforms_for
from .service import ServiceStatus, StationData, service_status
from .state import FeedState
from .wmata import WmataError

STALE_AFTER_S = 60.0
INCIDENTS_STALE_AFTER_S = 180.0
UNAVAILABLE_AFTER_S = 600.0

NOTICE_NO_KEY = "No WMATA API key configured"
NOTICE_BAD_KEY = "WMATA rejected the API key"
NOTICE_LOADING = "Loading arrivals…"
NOTICE_UNAVAILABLE = "Live arrivals unavailable"


def effective_lines(config: Config, station: StationData | None) -> tuple[str, ...] | None:
    if config.board.lines:
        return config.board.lines
    if station is not None and station.lines:
        return station.lines
    return None


def _service(station: StationData | None, now_local: datetime) -> ServiceStatus | None:
    if station is None:
        return None
    try:
        return service_status(station.times, station.code, now_local)
    except WmataError:
        return None


def _notice(config: Config, arrivals: FeedState, age: float | None, has_trains: bool,
            service: ServiceStatus | None) -> str | None:
    if config.api_key is None:
        return NOTICE_NO_KEY
    if arrivals.value is None:
        if arrivals.error_kind == "api_key":
            return NOTICE_BAD_KEY
        return NOTICE_UNAVAILABLE if arrivals.error else NOTICE_LOADING
    if age is not None and age > UNAVAILABLE_AFTER_S:
        return NOTICE_UNAVAILABLE
    if not has_trains and service is not None and not service.in_service and service.resumes:
        return f"No trains · service resumes {service.resumes}"
    return None


def build_board(*, config: Config, arrivals: FeedState, incidents: FeedState, station: FeedState,
                now: float, now_local: datetime, version: str) -> dict:
    code = config.board.station
    info: StationData | None = station.value
    lines = effective_lines(config, info)

    trains = [t for t in (arrivals.value or []) if t.station == code and (lines is None or t.line in lines)]
    service = _service(info, now_local)
    age = arrivals.age(now)
    notice = _notice(config, arrivals, age, bool(trains), service)
    if notice in (NOTICE_NO_KEY, NOTICE_BAD_KEY, NOTICE_UNAVAILABLE, NOTICE_LOADING):
        trains = []

    platforms = platforms_for(trains, code, config.platforms.get(code, {}),
                              config.board.rows_per_direction)
    alerts = alerts_for(incidents.value or [], lines)

    return {
        "station": {"code": code, "name": info.name if info else code},
        "timezone": config.board.timezone,
        "generated_at": now_local.isoformat(timespec="seconds"),
        "version": version,
        "platforms": [p.as_json() for p in platforms],
        "notice": notice,
        "alerts": [a.as_json() for a in alerts],
        "service": service.as_json() if service else None,
        "freshness": {
            "arrivals": arrivals.freshness(now, STALE_AFTER_S),
            "incidents": incidents.freshness(now, INCIDENTS_STALE_AFTER_S),
        },
    }
```
Note `test_no_key`: with no key the notice is `NOTICE_NO_KEY` regardless of feed state. `test_lines_omitted_uses_station_lines`: station lines are OR/SV, so the RD alert (id ending `2`) is filtered.

- [ ] **Step 5: Run** → PASS.

- [ ] **Step 6: Implement `src/wmata_board/feeds.py`**
```python
"""Wire the client to Feed objects. The only module that knows which
endpoints feed which parts of the board."""

from __future__ import annotations

import time
from collections.abc import Callable

from .config import Config
from .incidents import parse_incidents
from .poller import Feed
from .predictions import parse_predictions
from .service import station_data

STATION_CADENCE_S = 86400.0   # names, lines and first/last trains change rarely


def build_feeds(config: Config, client, *, clock: Callable[[], float] = time.monotonic) -> dict[str, Feed]:
    stations = list(config.board.stations)
    code = config.board.station
    idle = config.polling.idle_after

    async def arrivals():
        return parse_predictions(await client.predictions(stations), stations)

    async def incidents():
        return parse_incidents(await client.incidents())

    async def station():
        return station_data(code, await client.station_info(code), await client.station_times(code))

    return {
        "arrivals": Feed("arrivals", arrivals, config.polling.arrivals, idle_after=idle, clock=clock),
        "incidents": Feed("incidents", incidents, config.polling.incidents, idle_after=idle, clock=clock),
        "station": Feed("station", station, STATION_CADENCE_S, gated=False, clock=clock),
    }
```

- [ ] **Step 7: Failing app tests** — `tests/test_app.py`:
```python
import asyncio

import pytest
from fastapi.testclient import TestClient

from helpers import arrivals_state, config, incidents_state, station_state

from wmata_board.app import create_app
from wmata_board.fixtures import FixtureClient
from wmata_board.feeds import build_feeds
from wmata_board.poller import Feed


class Clock:
    t = 110.0

    def __call__(self):
        return self.t


@pytest.fixture
def app(fixtures):
    cfg = config()
    clock = Clock()
    feeds = build_feeds(cfg, FixtureClient(fixtures), clock=clock)
    feeds["arrivals"].state = arrivals_state()
    feeds["incidents"].state = incidents_state()
    feeds["station"].state = station_state()
    return create_app(cfg, FixtureClient(fixtures), feeds=feeds, version="test",
                      fresh_wait_s=0, start_polling=False, clock=clock)


def test_board_endpoint(app):
    with TestClient(app) as c:
        r = c.get("/api/board")
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("no-store")
    body = r.json()
    assert body["station"]["name"] == "Court House"
    assert body["version"] == "test"
    assert len(body["platforms"]) == 2


def test_board_request_marks_feeds_wanted(app):
    feeds = app.state.feeds
    assert not feeds["arrivals"].wanted()
    with TestClient(app) as c:
        c.get("/api/board")
    assert feeds["arrivals"].wanted() and feeds["incidents"].wanted()


def test_healthz(app):
    with TestClient(app) as c:
        body = c.get("/healthz").json()
    assert body["ok"] is True
    assert body["api_key"] is True
    assert body["feeds"]["arrivals"] == {"age_s": 10, "error": None}
    assert set(body["feeds"]) >= {"arrivals", "incidents", "station"}


def test_index_served(app):
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


async def test_first_request_after_idle_waits_for_fresh_data(fixtures):
    """Review focus 3: switching to the board must not show stale minutes for 5 s."""
    cfg = config()
    calls = []

    async def slow_fetch():
        await asyncio.sleep(0.05)
        calls.append(1)
        return arrivals_state().value     # real trains, so no "closed" notice at night

    feeds = build_feeds(cfg, FixtureClient(fixtures))
    feeds["arrivals"] = Feed("arrivals", slow_fetch, 20.0)
    app = create_app(cfg, FixtureClient(fixtures), feeds=feeds, fresh_wait_s=2.0)
    import httpx
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            body = (await c.get("/api/board")).json()
    assert calls == [1]
    assert body["notice"] is None          # fetched before answering, not "Loading"
```

- [ ] **Step 8: Implement `src/wmata_board/app.py`**
```python
"""HTTP front end: JSON endpoints, the two pages, static files.

Deliberately thin -- all decisions live in board.py and the pure modules.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .board import build_board
from .config import Config
from .feeds import build_feeds
from .poller import Feed, Poller

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"
DATA_DIR = PROJECT_ROOT / "data"
NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


class _NoStoreStaticFiles(StaticFiles):
    """What is on screen must match what is on disk after a deploy."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


def create_app(config: Config, client, *, feeds: dict[str, Feed] | None = None,
               version: str = __version__, fresh_wait_s: float = 3.0,
               start_polling: bool = True, data_dir: Path = DATA_DIR,
               clock: Callable[[], float] = time.monotonic) -> FastAPI:
    feeds = feeds if feeds is not None else build_feeds(config, client, clock=clock)
    poller = Poller(feeds)
    tz = ZoneInfo(config.board.timezone)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_polling:
            poller.start()
        try:
            yield
        finally:
            await poller.stop()
            await client.aclose()

    app = FastAPI(title="wmata-board", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.feeds = feeds
    app.state.data_dir = data_dir

    async def want(*names: str) -> None:
        """Mark feeds wanted; if one had gone idle and is due, wait (briefly)
        for its fetch so the first screen after switching is fresh."""
        waits = []
        for name in names:
            feed = feeds[name]
            if feed.want() and feed.due() and fresh_wait_s > 0:
                waits.append(feed.wait_for_update(fresh_wait_s))
        if waits:
            await asyncio.gather(*waits)

    @app.get("/api/board")
    async def board():
        await want("arrivals", "incidents")
        body = build_board(config=config, arrivals=feeds["arrivals"].state,
                           incidents=feeds["incidents"].state, station=feeds["station"].state,
                           now=clock(), now_local=datetime.now(tz), version=version)
        return JSONResponse(body, headers=NO_STORE)

    @app.get("/healthz")
    async def healthz():
        now = clock()
        return JSONResponse({
            "ok": True, "version": version, "api_key": config.api_key is not None,
            "feeds": {name: {"age_s": None if (a := f.state.age(now)) is None else int(a),
                             "error": f.state.error_kind} for name, f in feeds.items()},
        }, headers=NO_STORE)

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html", headers=NO_STORE)

    app.mount("/static", _NoStoreStaticFiles(directory=WEB_DIR), name="static")
    return app
```

- [ ] **Step 9: Implement `src/wmata_board/__main__.py`**
```python
"""Entry point: `python -m wmata_board [--config config.toml] [--fixtures DIR]`."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from . import __version__
from .app import PROJECT_ROOT, create_app
from .config import ConfigError, load_config
from .fixtures import FixtureClient
from .wmata import WmataClient

DEFAULT_CONFIG = PROJECT_ROOT / "config.toml"
log = logging.getLogger("wmata_board")


def build_version() -> str:
    """Changes on every deploy, so open pages know to reload themselves."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    return f"{__version__}+{sha or int(time.time())}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wmata_board", description="Court House departure board.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fixtures", type=Path, default=None,
                        help="replay recorded responses from this directory instead of calling WMATA")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-level", default="info",
                        choices=["critical", "error", "warning", "info", "debug"])
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.fixtures:
        client = FixtureClient(args.fixtures)
        log.info("fixtures mode: replaying %s", args.fixtures)
        if config.api_key is None:   # fixtures need no key, but the board would say "no key"
            from dataclasses import replace
            config = replace(config, api_key="fixtures")
    else:
        client = WmataClient(config.api_key)
        if config.api_key is None:
            log.warning("no WMATA_API_KEY set: the board will say so until one is configured")

    host = args.host or config.server.host
    port = args.port or config.server.port
    log.info("wmata-board on http://%s:%d/ (station %s)", host, port, config.board.station)
    uvicorn.run(create_app(config, client, version=build_version()),
                host=host, port=port, log_level=args.log_level, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
`Config` is a frozen dataclass (not slots), so `dataclasses.replace` works and keeps `api_key` out of reprs.

- [ ] **Step 10: Run everything**: `.venv/Scripts/python -m pytest -q` → all PASS. Then smoke-run fixtures mode: `.venv/Scripts/python -m wmata_board --fixtures tests/fixtures --port 8766` in the background, `curl -s localhost:8766/api/board` shows two platforms + 2 alerts, `curl -s localhost:8766/healthz` ok; stop the server.

- [ ] **Step 11: Commit** `git add src tests web/index.html && git commit -m "Board payload, app routes, and fixtures-mode CLI"`

---

# Milestone 2 — Wall board page

### Task 8: Wall board (arrivals, clock, stale pill, closed state)

**Files:**
- Create: `package.json`, `web/format.js`, `web/render.js`, `web/board.js`, `web/board.css`, `web/fonts/inter-latin-{500,600,700,800}-normal.woff2`, `tests/js/format.test.js`, `tests/js/render.test.js`, `tests/test_web_assets.py`
- Replace: `web/index.html`

**Interfaces:**
- Consumes: `/api/board` (Task 7).
- Produces (ES modules):
  - `format.js`: `LINE_COLORS: {RD: [bg, fg], ...}`, `LINE_LETTER`, `minuteParts(display) -> {big, unit, now}`, `pillState({nowMs, lastOkMs, startMs, arrivalsAgeS}) -> {kind: "hidden"|"amber"|"red", text}`, `formatClock(date, timeZone) -> "10:46 PM"`, `alertIndex(count, nowMs, periodMs=10000) -> number` (−1 when none), `escapeHtml(s)`, `OFFLINE_AFTER_MS = 15000`, `STALE_AFTER_S = 60`.
  - `render.js`: `chip(line, cls="chip") -> html`, `arrivalsHtml(board) -> html`.
  - `board.js`: no exports; polls `/api/board` every 5 s, reloads on version change.
  - Page DOM ids used by later tasks: `#stage`, `#station`, `#pill`, `#clock`, `#alert` (empty, hidden; Task 9 fills it), `#arrivals`, `#map` (empty panel; Task 15 fills it).

- [ ] **Step 1: Vendor Inter.** Download (curl -fL) `https://cdn.jsdelivr.net/npm/@fontsource/inter@5.1.1/files/inter-latin-{500,600,700,800}-normal.woff2` into `web/fonts/`. Verify each is > 10 kB and starts with bytes `wOF2`. Add `web/fonts/LICENSE.txt` with one line: `Inter by Rasmus Andersson, SIL Open Font License 1.1 (https://github.com/rsms/inter). Files from @fontsource/inter 5.1.1.`

- [ ] **Step 2: `package.json`** (only for `node --test`; nothing is installed):
```json
{
  "private": true,
  "type": "module",
  "scripts": { "test": "node --test tests/js/" }
}
```

- [ ] **Step 3: Failing JS tests** — `tests/js/format.test.js`:
```js
import test from "node:test";
import assert from "node:assert/strict";
import { minuteParts, pillState, formatClock, alertIndex, escapeHtml, LINE_COLORS } from "../../web/format.js";

test("minuteParts", () => {
  assert.deepEqual(minuteParts("BRD"), { big: "BRD", unit: "", now: true });
  assert.deepEqual(minuteParts("ARR"), { big: "ARR", unit: "", now: true });
  assert.deepEqual(minuteParts("7"), { big: "7", unit: "min", now: false });
  assert.deepEqual(minuteParts("—"), { big: "—", unit: "", now: false });
  assert.deepEqual(minuteParts(undefined), { big: "—", unit: "", now: false });
});

test("pill hidden when fresh", () => {
  assert.equal(pillState({ nowMs: 10_000, lastOkMs: 9_000, startMs: 0, arrivalsAgeS: 20 }).kind, "hidden");
});

test("pill amber when arrivals older than 60 s, counting time since last response", () => {
  const p = pillState({ nowMs: 100_000, lastOkMs: 95_000, startMs: 0, arrivalsAgeS: 58 });
  assert.equal(p.kind, "amber");
  assert.equal(p.text, "Updated 1 min ago");
  assert.equal(pillState({ nowMs: 0, lastOkMs: 0, startMs: 0, arrivalsAgeS: 185 }).text, "Updated 3 min ago");
});

test("pill red when backend unreachable for 15 s", () => {
  assert.deepEqual(pillState({ nowMs: 30_000, lastOkMs: 10_000, startMs: 0, arrivalsAgeS: 5 }),
                   { kind: "red", text: "Board offline" });
  // never reached since page start
  assert.equal(pillState({ nowMs: 16_000, lastOkMs: null, startMs: 0, arrivalsAgeS: null }).kind, "red");
  assert.equal(pillState({ nowMs: 5_000, lastOkMs: null, startMs: 0, arrivalsAgeS: null }).kind, "hidden");
});

test("formatClock in the board's timezone", () => {
  const d = new Date("2026-10-21T02:46:00Z");   // 10:46 PM EDT
  assert.equal(formatClock(d, "America/New_York"), "10:46 PM");
});

test("alertIndex rotates every 10 s", () => {
  assert.equal(alertIndex(0, 123), -1);
  assert.equal(alertIndex(1, 999_999), 0);
  assert.equal(alertIndex(3, 0), 0);
  assert.equal(alertIndex(3, 10_000), 1);
  assert.equal(alertIndex(3, 25_000), 2);
  assert.equal(alertIndex(3, 30_000), 0);
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<a href="x">&'</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;");
});

test("line colors cover all six lines", () => {
  assert.deepEqual(Object.keys(LINE_COLORS).sort(), ["BL", "GR", "OR", "RD", "SV", "YL"]);
});
```
`tests/js/render.test.js`:
```js
import test from "node:test";
import assert from "node:assert/strict";
import { arrivalsHtml, chip } from "../../web/render.js";

const board = (over = {}) => ({
  notice: null,
  platforms: [
    { group: "1", label: "To Washington · New Carrollton", trains: [
      { line: "SV", cars: 6, destination: "New Carrollton", minutes: 0, display: "BRD" },
      { line: "OR", cars: 8, destination: "New Carrollton", minutes: 9, display: "9" },
      { line: "OR", cars: null, destination: "<b>x</b>", minutes: null, display: "—" }] },
    { group: "2", label: "To Vienna · Ashburn", trains: [] }],
  ...over,
});

test("rows render chip, destination, cars and minutes", () => {
  const html = arrivalsHtml(board());
  assert.match(html, /To Washington · New Carrollton/);
  assert.match(html, /class="min now">BRD</);
  assert.match(html, /9<small>min<\/small>/);
  assert.match(html, /6 car/);
  assert.match(html, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.doesNotMatch(html, /null car/);
});

test("empty platform says so", () => {
  assert.match(arrivalsHtml(board()), /No trains predicted/);
});

test("notice replaces the rows", () => {
  const html = arrivalsHtml(board({ notice: "No trains · service resumes 5:19 AM" }));
  assert.match(html, /class="notice"/);
  assert.match(html, /service resumes 5:19 AM/);
  assert.doesNotMatch(html, /class="row"/);
});

test("chip uses line colors", () => {
  assert.equal(chip("OR"), '<span class="chip" style="background:#ed8b00;color:#111">OR</span>');
  assert.match(chip("ZZ"), /background:#3b4a5e/);
});
```

- [ ] **Step 4: Run** `node --test tests/js/` → FAIL (modules missing).

- [ ] **Step 5: Implement `web/format.js`**
```js
// Pure helpers shared by the wall board and the phone view (node --test).

export const LINE_COLORS = {
  RD: ["#c80f2d", "#fff"], OR: ["#ed8b00", "#111"], SV: ["#919d9d", "#111"],
  BL: ["#009cde", "#fff"], GR: ["#00b140", "#fff"], YL: ["#ffd100", "#111"],
};
export const LINE_LETTER = { RD: "R", OR: "O", SV: "S", BL: "B", GR: "G", YL: "Y" };
export const OFFLINE_AFTER_MS = 15000;
export const STALE_AFTER_S = 60;

export function minuteParts(display) {
  if (display === "BRD" || display === "ARR") return { big: display, unit: "", now: true };
  if (/^\d+$/.test(display ?? "")) return { big: display, unit: "min", now: false };
  return { big: "—", unit: "", now: false };
}

// Header pill: hidden when fresh, amber when the arrivals are old, red when
// the browser can't reach the board's own backend at all.
export function pillState({ nowMs, lastOkMs, startMs, arrivalsAgeS }) {
  const since = lastOkMs ?? startMs;
  if (nowMs - since > OFFLINE_AFTER_MS) return { kind: "red", text: "Board offline" };
  if (lastOkMs !== null && arrivalsAgeS !== null && arrivalsAgeS !== undefined) {
    const age = arrivalsAgeS + (nowMs - lastOkMs) / 1000;
    if (age > STALE_AFTER_S) return { kind: "amber", text: `Updated ${Math.max(1, Math.floor(age / 60))} min ago` };
  }
  return { kind: "hidden", text: "" };
}

const clockFormats = new Map();
export function formatClock(date, timeZone) {
  if (!clockFormats.has(timeZone)) {
    clockFormats.set(timeZone, new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone }));
  }
  // Newer ICU puts a narrow no-break space before AM/PM; normalize it.
  return clockFormats.get(timeZone).format(date).replace(/ /g, " ");
}

export function alertIndex(count, nowMs, periodMs = 10000) {
  return count ? Math.floor(nowMs / periodMs) % count : -1;
}

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ESC[c]);
}
```

`web/render.js`:
```js
// HTML builders shared by the wall and the phone. Strings only, no DOM, so
// they run under node --test.
import { LINE_COLORS, minuteParts, escapeHtml } from "./format.js";

export function chip(line, cls = "chip") {
  const [bg, fg] = LINE_COLORS[line] || ["#3b4a5e", "#fff"];
  return `<span class="${cls}" style="background:${bg};color:${fg}">${escapeHtml(line)}</span>`;
}

function rowHtml(t) {
  const m = minuteParts(t.display);
  const cars = t.cars ? `${t.cars} car` : "";
  const unit = m.unit ? `<small>${m.unit}</small>` : "";
  return `<div class="row">${chip(t.line)}` +
    `<span class="dest">${escapeHtml(t.destination)}<span class="cars">${cars}</span></span>` +
    `<span class="min${m.now ? " now" : ""}">${escapeHtml(m.big)}${unit}</span></div>`;
}

export function arrivalsHtml(board) {
  if (board.notice) return `<div class="notice">${escapeHtml(board.notice)}</div>`;
  return board.platforms.map(p =>
    `<section class="plat"><h2>${escapeHtml(p.label)}</h2>` +
    (p.trains.length ? p.trains.map(rowHtml).join("") : `<div class="row empty">No trains predicted</div>`) +
    `</section>`).join("");
}
```

- [ ] **Step 6: Run** `node --test tests/js/` → PASS.

- [ ] **Step 7: Page.** `web/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Court House</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="/static/board.css">
</head>
<body>
  <div id="stage">
    <header class="hdr">
      <span id="station" class="stn">Court House</span>
      <span class="right"><span id="pill" class="pill" hidden></span><span id="clock" class="clk"></span></span>
    </header>
    <div id="alert" class="alert" hidden></div>
    <main class="split">
      <div id="arrivals" class="arr"></div>
      <div id="map" class="mapbox"></div>
    </main>
  </div>
  <script type="module" src="/static/board.js"></script>
</body>
</html>
```

`web/board.css` (fixed 1920×1080 stage scaled to fit; sizes from the approved prototype, in cqw so they scale with the stage):
```css
@font-face { font-family: Inter; font-weight: 500; src: url(fonts/inter-latin-500-normal.woff2) format("woff2"); }
@font-face { font-family: Inter; font-weight: 600; src: url(fonts/inter-latin-600-normal.woff2) format("woff2"); }
@font-face { font-family: Inter; font-weight: 700; src: url(fonts/inter-latin-700-normal.woff2) format("woff2"); }
@font-face { font-family: Inter; font-weight: 800; src: url(fonts/inter-latin-800-normal.woff2) format("woff2"); }

html, body { margin: 0; height: 100%; background: #000; overflow: hidden; }
#stage { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; transform-origin: 0 0;
         container-type: inline-size; background: #0d1117; font-family: Inter, Helvetica, Arial, sans-serif;
         color: #f2f4f7; display: flex; flex-direction: column; }
#stage * { box-sizing: border-box; }

.hdr { display: flex; justify-content: space-between; align-items: baseline;
       border-bottom: .2cqw solid #2a313c; padding: 1.6cqw 3.2cqw .9cqw; }
.stn { font-size: 3.2cqw; font-weight: 800; }
.right { display: flex; align-items: baseline; gap: 1.4cqw; }
.clk { font-size: 2.6cqw; font-weight: 600; color: #aab3c0; font-variant-numeric: tabular-nums; }
.pill { font-size: 1.25cqw; font-weight: 700; padding: .35cqw 1cqw; border-radius: 99px; align-self: center; }
.pill.amber { background: #3a2e10; color: #ffd166; border: .1cqw solid #ffd166; }
.pill.red { background: #3a1214; color: #ff6b6b; border: .1cqw solid #ff6b6b; }

.split { flex: 1; display: grid; grid-template-columns: 54% 46%; min-height: 0; }
.arr { padding: 0 2.4cqw 0 3.2cqw; overflow: hidden; }
.plat h2 { font-size: 1.45cqw; font-weight: 700; color: #8b95a3; letter-spacing: .3cqw; text-transform: uppercase;
           margin: 1.6cqw 0 .3cqw; white-space: nowrap; }
.row { display: grid; grid-template-columns: 5.6cqw 1fr 10cqw; align-items: center;
       border-bottom: .1cqw solid #1c222b; height: 6.6cqw; }
.row:last-child { border-bottom: none; }
.row.empty { display: block; height: auto; padding: 1.4cqw 0; font-size: 1.8cqw; font-weight: 600; color: #5d6875; }
.chip { width: 4.2cqw; height: 4.2cqw; border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-size: 1.7cqw; font-weight: 800; }
.dest { font-weight: 700; font-size: 2.9cqw; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cars { font-size: 1.4cqw; font-weight: 600; color: #7d8794; display: block; }
.min { text-align: right; font-weight: 800; font-variant-numeric: tabular-nums; font-size: 3.8cqw; }
.min small { font-size: 1.6cqw; font-weight: 600; color: #8b95a3; margin-left: .4cqw; }
.min.now { color: #ffd166; }
.notice { margin-top: 6cqw; font-size: 2.6cqw; font-weight: 700; color: #aab3c0; line-height: 1.35; }

.mapbox { position: relative; border-left: .2cqw solid #1c222b; overflow: hidden; background: #0f151d; }
```

`web/board.js`:
```js
// Wall board: polls /api/board, renders arrivals, ticks the clock and pill.
import { formatClock, pillState } from "./format.js";
import { arrivalsHtml } from "./render.js";

const POLL_MS = 5000;
const $ = id => document.getElementById(id);
const stage = $("stage");

function fit() {
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
}
addEventListener("resize", fit);
fit();

const startMs = Date.now();
let board = null, lastOkMs = null, version = null;
export const hooks = { onBoard: [] };   // Task 9 subscribes the alert banner here

async function poll() {
  try {
    const r = await fetch("/api/board", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    board = await r.json();
    lastOkMs = Date.now();
    if (version === null) version = board.version;
    else if (board.version !== version) { location.reload(); return; }
    render();
  } catch (err) {
    console.warn("board poll failed", err);   // the pill turns red after OFFLINE_AFTER_MS
  } finally {
    setTimeout(poll, POLL_MS);
  }
}

function render() {
  $("station").textContent = board.station.name;
  document.title = board.station.name;
  $("arrivals").innerHTML = arrivalsHtml(board);
  hooks.onBoard.forEach(fn => fn(board));
}

function tick() {
  const now = Date.now();
  $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
  const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
  const pill = $("pill");
  pill.hidden = p.kind === "hidden";
  pill.className = `pill ${p.kind}`;
  pill.textContent = p.text;
}

setInterval(tick, 1000);
tick();
poll();
```

- [ ] **Step 8: Asset test** — `tests/test_web_assets.py` (guards against CDN references sneaking in and missing files):
```python
import re

from conftest import REPO

WEB = REPO / "web"


def test_no_remote_urls_in_pages():
    for path in list(WEB.glob("*.html")) + list(WEB.glob("*.css")) + list(WEB.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", text), f"remote URL in {path.name}"


def test_fonts_vendored():
    for weight in (500, 600, 700, 800):
        data = (WEB / "fonts" / f"inter-latin-{weight}-normal.woff2").read_bytes()
        assert data[:4] == b"wOF2" and len(data) > 10_000


def test_static_references_exist():
    for page in WEB.glob("*.html"):
        for ref in re.findall(r'(?:src|href)="/static/([^"]+)"', page.read_text(encoding="utf-8")):
            assert (WEB / ref).exists(), f"{page.name} references missing {ref}"
```

- [ ] **Step 9: Run** `.venv/Scripts/python -m pytest -q && node --test tests/js/` → PASS.

- [ ] **Step 10: Browser check (fixtures).** Start `.venv/Scripts/python -m wmata_board --fixtures tests/fixtures`; open `http://127.0.0.1:8766/` in Chrome at 1920×1080 (claude-in-chrome: resize window, screenshot). Expect: header "Court House" + clock; two platforms with three rows each, yellow BRD/ARR where present; map panel blank navy. Then stop the server and verify the red "Board offline" pill appears within ~15 s. Save screenshot notes in the task report.

- [ ] **Step 11: Commit** `git add package.json web tests && git commit -m "Wall board page: arrivals, clock, freshness pill"`

---

# Milestone 3 — Alerts

### Task 9: Alerts banner

**Files:**
- Modify: `web/render.js` (add `alertHtml`), `web/board.js` (banner rotation), `web/board.css` (banner styles), `tests/js/render.test.js`

**Interfaces:**
- Consumes: `hooks.onBoard` and `#alert` from Task 8; `alertIndex` from `format.js`.
- Produces: `render.js` `alertHtml(alert) -> html` (tag + line chips + text), used by the phone in Task 16.

- [ ] **Step 1: Failing test** — append to `tests/js/render.test.js`:
```js
import { alertHtml } from "../../web/render.js";

test("alert banner content", () => {
  const html = alertHtml({ id: "1", lines: ["OR", "SV"], text: "Trains every 15 <min>", updated: "" });
  assert.match(html, /<span class="tag">ALERT<\/span>/);
  assert.equal((html.match(/class="chip sm"/g) || []).length, 2);
  assert.match(html, /<span class="atext">Trains every 15 &lt;min&gt;<\/span>/);
});
```
(Move the new import up beside the existing `render.js` import.)

- [ ] **Step 2: Run** `node --test tests/js/` → FAIL (`alertHtml` not exported).

- [ ] **Step 3: Implement** — add to `web/render.js`:
```js
export function alertHtml(alert) {
  return `<span class="tag">ALERT</span>` +
    `<span class="achips">${alert.lines.map(l => chip(l, "chip sm")).join("")}</span>` +
    `<span class="atext">${escapeHtml(alert.text)}</span>`;
}
```
Add to `web/board.js` — the block goes after the `tick` definition and before the final `setInterval(tick, 1000); tick(); poll();` lines — and call `renderAlert()` at the end of `tick()`:
```js
import { alertIndex } from "./format.js";
import { alertHtml } from "./render.js";

let alerts = [], shownKey = null;
hooks.onBoard.push(b => { alerts = b.alerts || []; renderAlert(); });

// Several alerts rotate every 10 s; none -> no banner and the panels below
// reclaim the space (the map panel re-fits itself via its ResizeObserver).
function renderAlert() {
  const banner = $("alert");
  const i = alertIndex(alerts.length, Date.now());
  if (i < 0) { banner.hidden = true; shownKey = null; return; }
  const a = alerts[i], key = `${a.id}|${a.updated}|${a.text}`;
  if (key !== shownKey) { banner.innerHTML = alertHtml(a); shownKey = key; }
  banner.hidden = false;
}
```
(Merge the imports into the existing import lines rather than duplicating them.)

Append to `web/board.css`:
```css
.alert { display: flex; align-items: center; gap: 1.2cqw; background: #f5a623; color: #111;
         padding: .9cqw 3.2cqw; }
.alert[hidden] { display: none; }
.alert .tag { background: #111; color: #f5a623; font-weight: 800; font-size: 1.2cqw; letter-spacing: .25cqw;
              padding: .35cqw .8cqw; border-radius: .4cqw; flex: none; }
.alert .achips { display: flex; gap: .5cqw; flex: none; }
.chip.sm { width: 2.4cqw; height: 2.4cqw; font-size: 1cqw; }
.alert .atext { font-size: 1.6cqw; font-weight: 700; line-height: 1.3; display: -webkit-box;
                -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
```

- [ ] **Step 4: Run** `node --test tests/js/ && .venv/Scripts/python -m pytest -q` → PASS.

- [ ] **Step 5: Browser check (fixtures).** Fixtures `incidents.json` has two OR/SV alerts: banner shows under the header, rotates between them every 10 s, text ≤ 2 lines. Then copy `incidents_empty.json` over a temp fixtures dir's `incidents.json` (use a copy of `tests/fixtures` in the scratchpad, not the repo) and confirm the banner disappears and the panels grow.

- [ ] **Step 6: Commit** `git add web tests/js && git commit -m "Alert banner with rotation"`

---

# Milestone 4 — Deploy (board usable on the wall)

### Task 10: systemd unit, README, record tool, deploy to the Pi, kiosk-selector target

**Files:**
- Create: `deploy/wmata-board.service`, `tools/record_fixtures.py`, `README.md` (replace stub)
- Pi-side (not in this repo): `~/kiosk-selector/targets.py`

**Interfaces:**
- Consumes: the CLI from Task 7.
- Produces: running `wmata-board.service` on the Pi at `127.0.0.1:8766`; kiosk-selector target `metro`.

- [ ] **Step 1: `deploy/wmata-board.service`**
```ini
[Unit]
Description=wmata-board -- Court House departure board
Documentation=file:%h/wmata-board/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
WorkingDirectory=%h/wmata-board
# WMATA_API_KEY lives outside the repo (chmod 600), like ~/map-journal.env.
EnvironmentFile=%h/wmata-board.env
ExecStart=%h/wmata-board/.venv/bin/python -m wmata_board --config %h/wmata-board/config.toml
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

- [ ] **Step 2: `tools/record_fixtures.py`** — captures live responses into a fixtures dir (run on the Pi with the env file loaded). Never prints the key.
```python
"""Capture live WMATA responses as test fixtures.

    set -a; . ~/wmata-board.env; set +a
    .venv/bin/python tools/record_fixtures.py tests/fixtures --station K01 --positions 12

Writes predictions_<code>.json, incidents.json (only with --incidents, since
the sample one is hand-made), station_info_<code>.json, station_times_<code>.json
and positions/vp_<ms>.pb snapshots 5 s apart.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from wmata_board.wmata import WmataClient


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--station", default="K01")
    p.add_argument("--positions", type=int, default=0, help="number of GTFS-RT snapshots to record")
    p.add_argument("--incidents", action="store_true", help="overwrite incidents.json with the live feed")
    args = p.parse_args()

    key = os.environ.get("WMATA_API_KEY")
    if not key:
        raise SystemExit("WMATA_API_KEY is not set")
    client = WmataClient(key)
    out, code = args.out, args.station
    out.mkdir(parents=True, exist_ok=True)

    def save(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print("wrote", out / name)

    save(f"predictions_{code}.json", await client.predictions([code]))
    save(f"station_info_{code}.json", await client.station_info(code))
    save(f"station_times_{code}.json", await client.station_times(code))
    if args.incidents:
        save("incidents.json", await client.incidents())
    if args.positions:
        (out / "positions").mkdir(exist_ok=True)
        for _ in range(args.positions):
            path = out / "positions" / f"vp_{int(time.time() * 1000)}.pb"
            path.write_bytes(await client.vehicle_positions())
            print("wrote", path)
            await asyncio.sleep(5)
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: README.md** — sections: What it is (one paragraph + URLs: wall via kiosk-selector `metro`, phone `https://raspberrypi.tail7b0b4d.ts.net:8446/phone`); Local development (`python -m venv .venv`, `pip install -e ".[dev]"`, `python -m wmata_board --fixtures tests/fixtures`, tests: `pytest`, `node --test tests/js/`); Configuration (point at `config.toml` comments; key in `WMATA_API_KEY` via `~/wmata-board.env` on the Pi or `.env` locally); Pi setup (clone, venv, `pip install -e .`, copy unit to `~/.config/systemd/user/`, `systemctl --user daemon-reload && systemctl --user enable --now wmata-board`, basemap: `tools/build_basemap.sh`, tailscale serve command, kiosk-selector `metro` target); Deploy an update (`git push`, then `ssh raspberrypi 'cd ~/wmata-board && git pull --ff-only && .venv/bin/pip install -e . -q && systemctl --user restart wmata-board'`; pages reload themselves on the new version); Troubleshooting (`journalctl --user -u wmata-board -f`; `curl -s localhost:8766/healthz`; pill meanings: amber = WMATA data old, red = page can't reach the service; "WMATA rejected the API key" → check `~/wmata-board.env`; WMATA quirks: `NewCrlton`/`LastTrain` aliases live in `predictions.py` `DESTINATION_ALIASES`); Data & licenses (WMATA data terms; basemap © OpenStreetMap contributors via Protomaps, ODbL; Inter OFL; MapLibre BSD-3).

- [ ] **Step 4: Verify locally**: `.venv/Scripts/python -m pytest -q && node --test tests/js/`. Commit: `git add deploy tools README.md && git commit -m "systemd unit, fixture recorder, README"`.

- [ ] **Step 5: Push**: `git push origin main` (if work happened on a branch, fast-forward `main` to it first).

- [ ] **Step 6: Install on the Pi** (over `ssh raspberrypi`):
```bash
cd ~ && [ -d wmata-board ] || git clone git@github.com:ethanleboeuf/wmata-board.git
cd ~/wmata-board && git pull --ff-only
python3 -m venv .venv && .venv/bin/pip install -q -e .
cp deploy/wmata-board.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now wmata-board
sleep 4; systemctl --user is-active wmata-board; curl -s localhost:8766/healthz
```
Expected: `active`; healthz `ok: true, api_key: true`. Then `curl -s localhost:8766/api/board | head -c 600` shows real K01 trains (first board request wakes the feeds). Check `journalctl --user -u wmata-board -n 30` has no tracebacks and no key.

- [ ] **Step 7: kiosk-selector target.** On the Pi, in `~/kiosk-selector`: read `targets.py` and its tests (`grep -rn TARGETS tests`), add `"metro": "http://localhost:8766/",` after `"stats"` with a one-line comment (`# WMATA departure board (~/wmata-board), port 8766`), run its tests (`venv/bin/python -m pytest -q`), commit in that repo (`git commit -am "Add metro target (wmata-board)"`), `systemctl --user restart kiosk-selector`. Confirm the phone page at `:8445` lists `metro` (`curl -sk https://raspberrypi.tail7b0b4d.ts.net:8445/ | grep -c metro` from the dev PC, or `curl -s localhost:8767/` on the Pi).

- [ ] **Step 8: Wall check without disturbing the room for long.** Record what the kiosk currently shows (`~/kiosk-selector` has `cdp.current_page()`: `cd ~/kiosk-selector && venv/bin/python -c "import cdp; print(cdp.current_page()['url'])"`), switch to metro (`curl -s -X POST localhost:8767/switch/metro`), take a CDP screenshot to verify (`Page.captureScreenshot` via a short python using `cdp.py`'s websocket helper, or skip the screenshot if that helper doesn't exist and instead `cdp.evaluate("document.querySelector('#arrivals').innerText")`), then navigate back to the recorded URL (`cdp.navigate(url)`). Report what was seen.

---

# Milestone 5 — Live map

### Task 11: Train positions decode + `/api/positions`

**Files:**
- Create: `src/wmata_board/positions.py`, `tests/test_positions.py`
- Modify: `src/wmata_board/feeds.py` (add `positions` feed), `src/wmata_board/app.py` (add route), `tests/test_app.py`

**Interfaces:**
- Consumes: `ROUTE_LINES` (Task 1), `WmataError`, `Feed`.
- Produces: `Vehicle(id, line, lat, lon, heading: float|None, cars: int|None)` + `.as_json()`; `PositionsSnapshot(feed_timestamp: int, vehicles: tuple[Vehicle,...])`; `decode_positions(data: bytes) -> PositionsSnapshot`; `cars_from_plate(plate: str) -> int|None`; `POSITIONS_STALE_AFTER_S = 120`. `/api/positions` → `{fetched_at: iso|None, feed_timestamp: int|None, age_s: int|None, stale: bool, error: str|None, vehicles: [{id, line, lat, lon, heading, cars}]}` (stale is true when never fetched, too).

- [ ] **Step 1: Failing tests** — `tests/test_positions.py`:
```python
import pytest
from google.transit import gtfs_realtime_pb2

from wmata_board.positions import cars_from_plate, decode_positions
from wmata_board.wmata import WmataError


@pytest.mark.parametrize("plate, cars", [
    ("8_7202-7203.7111-7110.7341-7340.7299-7298", 8), ("6_1", 6), ("", None), ("x_1", None), ("8", 8),
])
def test_cars_from_plate(plate, cars):
    assert cars_from_plate(plate) == cars


def feed(*entities, ts=1792551838):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = ts
    for i, (route, lat, lon, bearing, plate, has_pos) in enumerate(entities):
        e = msg.entity.add()
        e.id = f"e{i}"
        v = e.vehicle
        if route is not None:
            v.trip.route_id = route
        if has_pos:
            v.position.latitude, v.position.longitude = lat, lon
            if bearing is not None:
                v.position.bearing = bearing
        v.vehicle.id = f"v{i}"
        v.vehicle.license_plate = plate
    return msg.SerializeToString()


def test_synthetic_feed_filters_and_maps():
    data = feed(("ORANGE", 38.89, -77.08, 90.0, "8_1-2", True),
                ("SILVER", 38.90, -77.07, None, "", True),
                ("BUS", 38.9, -77.0, 0.0, "6_1", True),        # unknown route
                (None, 38.9, -77.0, 0.0, "6_1", True),         # no trip
                ("RED", 0, 0, 0.0, "6_1", False))              # no position
    snap = decode_positions(data)
    assert snap.feed_timestamp == 1792551838
    assert [(v.id, v.line, v.cars, v.heading) for v in snap.vehicles] == \
        [("v0", "OR", 8, 90.0), ("v1", "SV", None, None)]
    assert snap.vehicles[0].lat == pytest.approx(38.89, abs=1e-5)
    assert snap.vehicles[0].as_json() == {"id": "v0", "line": "OR", "lat": snap.vehicles[0].lat,
                                          "lon": snap.vehicles[0].lon, "heading": 90.0, "cars": 8}


def test_recorded_snapshot(fixtures):
    path = sorted((fixtures / "positions").glob("*.pb"))[0]
    snap = decode_positions(path.read_bytes())
    assert snap.feed_timestamp > 1_700_000_000
    assert len(snap.vehicles) > 20
    assert {v.line for v in snap.vehicles} <= {"RD", "OR", "SV", "BL", "GR", "YL"}
    assert {v.cars for v in snap.vehicles} <= {6, 8, None}
    assert all(38.5 < v.lat < 39.3 and -77.6 < v.lon < -76.7 for v in snap.vehicles)


def test_garbage_is_parse_error():
    with pytest.raises(WmataError) as err:
        decode_positions(b"\xff\xff\xff\xff")
    assert err.value.kind == "parse"
```
Append to `tests/test_app.py`:
```python
def test_positions_endpoint(app, fixtures):
    from wmata_board.positions import decode_positions
    from helpers import state
    path = sorted((fixtures / "positions").glob("*.pb"))[0]
    app.state.feeds["positions"].state = state(decode_positions(path.read_bytes()))
    with TestClient(app) as c:
        body = c.get("/api/positions").json()
    assert body["stale"] is False and body["age_s"] == 10
    assert body["feed_timestamp"] > 0
    assert len(body["vehicles"]) > 20
    assert set(body["vehicles"][0]) == {"id", "line", "lat", "lon", "heading", "cars"}
    assert app.state.feeds["positions"].wanted()


def test_positions_before_first_fetch(app):
    with TestClient(app) as c:
        body = c.get("/api/positions").json()
    assert body == {"fetched_at": None, "feed_timestamp": None, "age_s": None, "stale": True,
                    "error": None, "vehicles": []}
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement `src/wmata_board/positions.py`**
```python
"""GTFS-RT rail vehicle positions -> the trains the map draws. Pure.

`vehicle.license_plate` is "<cars>_<car numbers>" (e.g. "8_7202-7203...").
Only revenue trains on one of the six lines are kept.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from .lines import ROUTE_LINES
from .wmata import WmataError

POSITIONS_STALE_AFTER_S = 120.0


@dataclass(frozen=True, slots=True)
class Vehicle:
    id: str
    line: str
    lat: float
    lon: float
    heading: float | None
    cars: int | None

    def as_json(self) -> dict:
        return {"id": self.id, "line": self.line, "lat": self.lat, "lon": self.lon,
                "heading": self.heading, "cars": self.cars}


@dataclass(frozen=True, slots=True)
class PositionsSnapshot:
    feed_timestamp: int
    vehicles: tuple[Vehicle, ...]


def cars_from_plate(plate: str) -> int | None:
    head = (plate or "").split("_", 1)[0]
    return int(head) if head.isdigit() else None


def decode_positions(data: bytes) -> PositionsSnapshot:
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(data)
    except DecodeError:
        raise WmataError("parse", "bad GTFS-RT vehicle positions") from None
    vehicles = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        line = ROUTE_LINES.get(v.trip.route_id)
        if line is None or not v.HasField("position"):
            continue
        pos = v.position
        vehicles.append(Vehicle(
            id=v.vehicle.id or entity.id, line=line,
            lat=round(pos.latitude, 6), lon=round(pos.longitude, 6),
            heading=round(pos.bearing, 1) if pos.HasField("bearing") else None,
            cars=cars_from_plate(v.vehicle.license_plate),
        ))
    return PositionsSnapshot(int(feed.header.timestamp), tuple(vehicles))
```

In `feeds.py` add (import `decode_positions`):
```python
    async def positions():
        return decode_positions(await client.vehicle_positions())
```
and the dict entry `"positions": Feed("positions", positions, config.polling.positions, idle_after=idle, clock=clock),`.

In `app.py` add (import `POSITIONS_STALE_AFTER_S`):
```python
    @app.get("/api/positions")
    async def positions():
        await want("positions")
        st = feeds["positions"].state
        age = st.age(clock())
        snap = st.value
        return JSONResponse({
            "fetched_at": st.fetched_wall.isoformat(timespec="seconds") if st.fetched_wall else None,
            "feed_timestamp": snap.feed_timestamp if snap else None,
            "age_s": None if age is None else int(age),
            "stale": age is None or age > POSITIONS_STALE_AFTER_S,
            "error": st.error_kind,
            "vehicles": [v.as_json() for v in snap.vehicles] if snap else [],
        }, headers=NO_STORE)
```
(`helpers.state()` leaves `fetched_wall` None, so `fetched_at` is None in the endpoint test — fine; the assertion doesn't check it.)

- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest -q` → PASS. **Step 5: Commit** `git add src tests && git commit -m "Decode GTFS-RT positions and serve /api/positions"`

---

### Task 12: Network geometry + `/api/network` + cache + `network.json` fixture

**Files:**
- Create: `src/wmata_board/network.py`, `tests/test_network.py`, `tests/fixtures/network.json` (generated)
- Modify: `feeds.py` (add `network` feed; `build_feeds(..., network_loader=...)`), `app.py` (route; pass loader), `__main__.py` (fixtures → `FixtureNetwork`, live → `NetworkCache`), `tests/test_app.py`

**Interfaces:**
- Consumes: `ROUTE_LINES`, `NORTH_SOUTH`, `WmataError`, `Feed`, `MapConfig`.
- Produces: `build_network(zip_bytes: bytes) -> {"lines": {code: [[lon, lat], ...]}, "stations": [{"codes": [...], "name", "lon", "lat", "transfer": bool}]}`; `simplify(points, eps)`; `NetworkCache(client, path: Path, *, max_age_s=86400, clock=time.time)` with `async load() -> dict`; `FixtureNetwork(path)` with `async load()`. `/api/network` → `{lines, stations, home: "K01", view: {bbox: [w,s,e,n]}, labels: [...], places: [{name, lat, lon}], landmarks: [{name, lat, lon, style}]}` or 503 `{"error": "network loading"}`.

- [ ] **Step 1: Failing tests** — `tests/test_network.py` (builds a tiny GTFS zip in memory):
```python
import io
import json
import zipfile

import pytest

from wmata_board.network import FixtureNetwork, NetworkCache, build_network, simplify
from wmata_board.wmata import WmataError


def csv(header, *rows):
    return "\n".join([header, *(",".join(map(str, r)) for r in rows)]) + "\n"


def gtfs_zip() -> bytes:
    files = {
        "routes.txt": csv("route_id,route_short_name,route_color", ("ORANGE", "O", "ED8B00"),
                          ("BLUE", "B", "009CDE"), ("GREEN", "G", "00B140"), ("SHUTTLE", "X", "000000")),
        "trips.txt": csv("route_id,service_id,trip_id,shape_id",
                         ("ORANGE", "s", "t1", "or_long"), ("ORANGE", "s", "t2", "or_short"),
                         ("BLUE", "s", "t3", "bl"), ("GREEN", "s", "t4", "gr"), ("SHUTTLE", "s", "t5", "x")),
        # or_long runs E->W in the file; build_network must flip it to W->E
        "shapes.txt": csv("shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled",
                          ("or_long", 38.90, -77.00, 1, 0), ("or_long", 38.90, -77.05, 2, 5),
                          ("or_long", 38.90, -77.10, 3, 10),
                          ("or_short", 38.90, -77.05, 1, 0), ("or_short", 38.90, -77.10, 2, 5),
                          ("bl", 38.85, -77.05, 1, 0), ("bl", 38.90, -77.05, 2, 6),
                          # gr runs N->S in the file; must become S->N
                          ("gr", 38.95, -77.02, 1, 0), ("gr", 38.85, -77.02, 2, 11),
                          ("x", 38.0, -77.0, 1, 0), ("x", 38.1, -77.0, 2, 1)),
        "stops.txt": csv("stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station",
                         ("STN_K01", "Court House", 38.90, -77.10, 1, ""),
                         ("STN_C05", "Rosslyn", 38.90, -77.05, 1, ""),
                         ("STN_A01_C01", "Metro Center", 38.90, -77.00, 1, ""),
                         ("STN_J02", "Van Dorn", 38.85, -77.05, 1, ""),
                         ("PF_K01_1", "Court House", 38.90, -77.10, 0, "STN_K01"),
                         ("PF_C05_1", "Rosslyn", 38.90, -77.05, 0, "STN_C05"),
                         ("PF_C01_1", "Metro Center", 38.90, -77.00, 0, "STN_A01_C01"),
                         ("PF_J02_1", "Van Dorn", 38.85, -77.05, 0, "STN_J02")),
        "stop_times.txt": csv("trip_id,arrival_time,departure_time,stop_id,stop_sequence",
                              ("t1", "", "", "PF_C01_1", 1), ("t1", "", "", "PF_C05_1", 2),
                              ("t1", "", "", "PF_K01_1", 3),
                              ("t3", "", "", "PF_J02_1", 1), ("t3", "", "", "PF_C05_1", 2)),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, "﻿" + text)   # WMATA's files carry a BOM
    return buf.getvalue()


@pytest.fixture
def net():
    return build_network(gtfs_zip())


def test_longest_shape_per_line_oriented(net):
    assert set(net["lines"]) == {"OR", "BL", "GR"}
    assert net["lines"]["OR"] == [[-77.1, 38.9], [-77.0, 38.9]]      # W->E, collinear midpoint simplified away
    assert net["lines"]["GR"][0][1] < net["lines"]["GR"][-1][1]       # S->N


def test_stations_and_transfers(net):
    by = {s["name"]: s for s in net["stations"]}
    assert set(by) == {"Court House", "Rosslyn", "Metro Center", "Van Dorn"}
    assert by["Metro Center"]["codes"] == ["A01", "C01"]
    assert by["Metro Center"]["transfer"] is True     # combined id
    assert by["Rosslyn"]["transfer"] is True          # three neighbours
    assert by["Court House"]["transfer"] is False
    assert by["Van Dorn"]["transfer"] is False
    assert by["Court House"]["lon"] == -77.1


def test_simplify_keeps_corners():
    pts = [(0, 0), (1, 0.000001), (2, 0), (2, 1)]
    assert simplify(pts, 0.001) == [(0, 0), (2, 0), (2, 1)]
    assert simplify([(0, 0)], 1) == [(0, 0)]


def test_fixture_network_is_real(fixtures):
    data = json.loads((fixtures / "network.json").read_text(encoding="utf-8"))
    assert set(data["lines"]) == {"RD", "OR", "SV", "BL", "GR", "YL"}
    assert len(data["stations"]) >= 95
    transfers = {c for s in data["stations"] if s["transfer"] for c in s["codes"]}
    assert {"C05", "A01", "C01", "D03", "F03", "B06", "E06", "K05"} <= transfers
    assert not {"K01", "K02", "K04"} & transfers


class FakeClient:
    def __init__(self, data=None, fail=False):
        self.calls, self.data, self.fail = 0, data, fail

    async def gtfs_static(self):
        self.calls += 1
        if self.fail:
            raise WmataError("network", "down")
        return self.data


async def test_cache_builds_then_reuses(tmp_path):
    client = FakeClient(gtfs_zip())
    clock = [1000.0]
    cache = NetworkCache(client, tmp_path / "network.json", clock=lambda: clock[0])
    first = await cache.load()
    assert client.calls == 1 and (tmp_path / "network.json").exists()
    assert await cache.load() == first and client.calls == 1
    clock[0] += 86401
    await cache.load()
    assert client.calls == 2


async def test_cache_survives_restart_and_download_failure(tmp_path):
    path = tmp_path / "network.json"
    await NetworkCache(FakeClient(gtfs_zip()), path, clock=lambda: 0.0).load()
    stale = NetworkCache(FakeClient(fail=True), path, clock=lambda: 10 * 86400.0)
    assert (await stale.load())["lines"]          # stale cache beats nothing
    with pytest.raises(WmataError):
        await NetworkCache(FakeClient(fail=True), tmp_path / "none.json").load()


async def test_fixture_network(fixtures):
    assert "lines" in await FixtureNetwork(fixtures / "network.json").load()
```
Append to `tests/test_app.py`:
```python
def test_network_endpoint(app, fixtures):
    import json
    from helpers import state
    app.state.feeds["network"].state = state(json.loads((fixtures / "network.json").read_text(encoding="utf-8")))
    with TestClient(app) as c:
        body = c.get("/api/network").json()
    assert body["home"] == "K01"
    assert body["view"] == {"bbox": [-77.122, 38.844, -76.978, 38.966]}
    assert body["labels"][0] == "K04"
    assert body["places"][0] == {"name": "GEORGETOWN", "lat": 38.9085, "lon": -77.0665}
    assert body["landmarks"][0]["style"] == "hospital"
    assert set(body["lines"]) == {"RD", "OR", "SV", "BL", "GR", "YL"}


def test_network_loading(app):
    with TestClient(app) as c:
        r = c.get("/api/network")
    assert r.status_code == 503
```
Update the `app` fixture in `tests/test_app.py` to pass a loader: `build_feeds(cfg, FixtureClient(fixtures), network_loader=FixtureNetwork(fixtures / "network.json"), clock=clock)` (import `FixtureNetwork`), and the same in `test_first_request_after_idle_waits_for_fresh_data`.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement `src/wmata_board/network.py`**
```python
"""Track geometry and stations from WMATA's rail GTFS static zip.

Per line: the longest shape (by shape_dist_traveled), oriented W->E (S->N
for Green/Yellow) so lines sharing track run the same way and their lane
offsets land on consistent sides, simplified to ~2 m.

Transfer stations: a combined stop_id (STN_A01_C01) or three or more
neighbouring stations across all lines (Rosslyn, Pentagon, East Falls
Church, King St, Stadium-Armory ...). Court House, with two neighbours, is not.

`python -m wmata_board.network rail.zip out.json` writes the fixture.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
import os
import sys
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path

from .lines import NORTH_SOUTH, ROUTE_LINES
from .wmata import WmataError

log = logging.getLogger("wmata_board.network")
SIMPLIFY_EPS_DEG = 0.00002
MAX_AGE_S = 86400.0


def _rows(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))


def simplify(points: list, eps: float) -> list:
    """Douglas-Peucker, iterative (shapes run to thousands of points)."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x0, y0), (x1, y1) = points[a], points[b]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1e-12
        best, best_d = None, eps
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / length
            if d > best_d:
                best, best_d = i, d
        if best is not None:
            keep[best] = True
            stack += [(a, best), (best, b)]
    return [p for p, k in zip(points, keep) if k]


def _orient(line: str, seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
    axis = 1 if line in NORTH_SOUTH else 0       # (lon, lat): compare lat for N-S lines
    return seq[::-1] if seq[0][axis] > seq[-1][axis] else seq


def build_network(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        route_line = {r["route_id"]: ROUTE_LINES[r["route_id"]]
                      for r in _rows(z, "routes.txt") if r["route_id"] in ROUTE_LINES}
        shapes_by_line: dict[str, set[str]] = defaultdict(set)
        trip_of_shape: dict[str, str] = {}
        for t in _rows(z, "trips.txt"):
            line = route_line.get(t["route_id"])
            if line:
                shapes_by_line[line].add(t["shape_id"])
                trip_of_shape.setdefault(t["shape_id"], t["trip_id"])

        wanted_shapes = set().union(*shapes_by_line.values()) if shapes_by_line else set()
        points: dict[str, list[tuple[int, float, float, float]]] = defaultdict(list)
        for r in _rows(z, "shapes.txt"):
            if r["shape_id"] in wanted_shapes:
                points[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lat"]),
                                              float(r["shape_pt_lon"]), float(r["shape_dist_traveled"] or 0)))

        lines = {}
        for line, sids in shapes_by_line.items():
            candidates = [s for s in sids if points.get(s)]
            if not candidates:
                continue
            best = max(candidates, key=lambda s: (max(p[3] for p in points[s]), len(points[s])))
            seq = [(lon, lat) for _, lat, lon, _ in sorted(points[best])]
            lines[line] = [[round(x, 6), round(y, 6)] for x, y in simplify(_orient(line, seq), SIMPLIFY_EPS_DEG)]

        stops = list(_rows(z, "stops.txt"))
        parent = {s["stop_id"]: s.get("parent_station", "") for s in stops}

        def station_of(stop_id: str) -> str:
            for _ in range(5):
                up = parent.get(stop_id, "")
                if not up:
                    break
                stop_id = up
            return stop_id

        trips = set(trip_of_shape.values())
        sequences: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for r in _rows(z, "stop_times.txt"):
            if r["trip_id"] in trips:
                sequences[r["trip_id"]].append((int(r["stop_sequence"]), station_of(r["stop_id"])))
        neighbours: dict[str, set[str]] = defaultdict(set)
        for seq in sequences.values():
            ordered = [s for _, s in sorted(seq)]
            for a, b in zip(ordered, ordered[1:]):
                if a != b:
                    neighbours[a].add(b)
                    neighbours[b].add(a)

        stations = []
        for s in stops:
            if s.get("location_type") != "1" or not s["stop_id"].startswith("STN_"):
                continue
            codes = s["stop_id"][4:].split("_")
            stations.append({"codes": codes, "name": s["stop_name"],
                             "lon": round(float(s["stop_lon"]), 6), "lat": round(float(s["stop_lat"]), 6),
                             "transfer": len(codes) > 1 or len(neighbours[s["stop_id"]]) >= 3})
    return {"lines": lines, "stations": stations}


class NetworkCache:
    """data/network.json, rebuilt from the GTFS static zip once a day. A stale
    cache is served if the download fails -- track geometry barely changes."""

    def __init__(self, client, path: Path, *, max_age_s: float = MAX_AGE_S,
                 clock: Callable[[], float] = time.time) -> None:
        self._client, self._path, self._max_age, self._clock = client, Path(path), max_age_s, clock
        self._memo: dict | None = None
        self._built_at: float | None = None

    def _read(self) -> tuple[dict, float] | None:
        try:
            blob = json.loads(self._path.read_text(encoding="utf-8"))
            return blob["network"], float(blob["built_at"])
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            return None

    async def load(self) -> dict:
        if self._memo is None and (cached := self._read()):
            self._memo, self._built_at = cached
        if self._memo is not None and self._clock() - self._built_at < self._max_age:
            return self._memo
        try:
            data = await self._client.gtfs_static()
            network = await asyncio.to_thread(build_network, data)
        except (WmataError, zipfile.BadZipFile, KeyError, ValueError) as exc:
            if self._memo is not None:
                log.warning("network refresh failed (%s); keeping cached copy", exc)
                return self._memo
            if isinstance(exc, WmataError):
                raise
            raise WmataError("parse", f"bad GTFS static zip: {exc}") from None
        self._memo, self._built_at = network, self._clock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"built_at": self._built_at, "network": network}), encoding="utf-8")
        os.replace(tmp, self._path)
        log.info("network rebuilt: %d lines, %d stations", len(network["lines"]), len(network["stations"]))
        return network


class FixtureNetwork:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def load(self) -> dict:
        return json.loads(self._path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.write_text(json.dumps(build_network(src.read_bytes()), separators=(",", ":")), encoding="utf-8")
    print("wrote", out)
```

- [ ] **Step 4: Generate the fixture**: `.venv/Scripts/python -m wmata_board.network .superpowers/prototypes/data/gtfs_dl/rail.zip tests/fixtures/network.json` — expect a file of roughly 50–250 kB. If `test_fixture_network_is_real` fails on the transfer set, print the station names flagged as transfers and their neighbour counts; adjust only the rule's threshold if the data truly differs, and record why in the module docstring.

- [ ] **Step 5: Wire it.** `feeds.build_feeds(config, client, *, network_loader=None, clock=...)`: when `network_loader` is given add `"network": Feed("network", network_loader.load, 3600.0, gated=False, clock=clock)` (hourly check; the cache decides when to download). In `app.create_app` add a `network_loader=None` keyword passed through to `build_feeds` when `feeds` is None, and the route:
```python
    @app.get("/api/network")
    async def network():
        feed = feeds.get("network")
        net = feed.state.value if feed else None
        if net is None:
            return JSONResponse({"error": "network loading"}, status_code=503, headers=NO_STORE)
        m = config.map
        return JSONResponse({
            **net,
            "home": config.board.station,
            "view": {"bbox": list(m.bbox)},
            "labels": list(m.labels),
            "places": [{"name": p.name, "lat": p.lat, "lon": p.lon} for p in m.places],
            "landmarks": [{"name": x.name, "lat": x.lat, "lon": x.lon, "style": x.style} for x in m.landmarks],
        }, headers={"Cache-Control": "max-age=600"})
```
In `__main__.py`: fixtures → `network_loader=FixtureNetwork(args.fixtures / "network.json")`; live → `NetworkCache(client, DATA_DIR / "network.json")`; pass to `create_app(..., network_loader=...)`.

- [ ] **Step 6: Run** `.venv/Scripts/python -m pytest -q` → PASS. **Step 7: Commit** `git add src tests && git commit -m "Network geometry from GTFS static with daily cache; /api/network"`

---

### Task 13: Basemap: build tool, style, vendored MapLibre/pmtiles, range serving

**Files:**
- Create: `tools/build_basemap.sh`, `web/style.json`, `web/vendor/maplibre-gl.js`, `web/vendor/maplibre-gl.css`, `web/vendor/pmtiles.js`, `web/vendor/LICENSES.txt`, `tests/test_basemap.py`
- Modify: `app.py` (`/basemap.pmtiles`)

**Interfaces:**
- Produces: `GET /basemap.pmtiles` with `Accept-Ranges: bytes`, 206 for `Range: bytes=a-b` / `bytes=a-` / `bytes=-n`, 416 for unsatisfiable, 404 when `data/basemap.pmtiles` is missing; HEAD supported. `web/style.json` with source id `protomaps` whose `url` is rewritten at runtime by `map.js`.

- [ ] **Step 1: Failing tests** — `tests/test_basemap.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from helpers import config

from conftest import REPO
from wmata_board.app import create_app
from wmata_board.fixtures import FixtureClient


@pytest.fixture
def client(tmp_path, fixtures):
    (tmp_path / "basemap.pmtiles").write_bytes(bytes(range(256)) * 4)   # 1024 bytes
    app = create_app(config(), FixtureClient(fixtures), start_polling=False, data_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_full_file(client):
    r = client.get("/basemap.pmtiles")
    assert r.status_code == 200 and len(r.content) == 1024
    assert r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("header, start, end", [("bytes=0-15", 0, 15), ("bytes=1000-", 1000, 1023),
                                                ("bytes=-24", 1000, 1023), ("bytes=10-5000", 10, 1023)])
def test_ranges(client, header, start, end):
    r = client.get("/basemap.pmtiles", headers={"Range": header})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes {start}-{end}/1024"
    assert r.content == (bytes(range(256)) * 4)[start:end + 1]


@pytest.mark.parametrize("header", ["bytes=2000-", "bytes=9-3", "items=0-1", "bytes=-"])
def test_bad_ranges(client, header):
    r = client.get("/basemap.pmtiles", headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1024"


def test_head(client):
    r = client.head("/basemap.pmtiles")
    assert r.status_code == 200 and r.headers["content-length"] == "1024"


def test_missing_basemap_is_404(tmp_path, fixtures):
    """Review focus 5: no basemap yet -> clean 404 the page can handle."""
    app = create_app(config(), FixtureClient(fixtures), start_polling=False, data_dir=tmp_path / "empty")
    with TestClient(app) as c:
        assert c.get("/basemap.pmtiles").status_code == 404
        assert c.head("/basemap.pmtiles").status_code == 404


def test_style_is_board_navy():
    style = json.loads((REPO / "web" / "style.json").read_text(encoding="utf-8"))
    assert style["version"] == 8
    assert "glyphs" not in style and "sprite" not in style        # no symbol layers
    assert all(layer["type"] != "symbol" for layer in style["layers"])
    colors = json.dumps(style)
    for c in ("#0f151d", "#0c2742", "#151e29", "#24324a", "#33465f"):
        assert c in colors
    assert "OpenStreetMap" in style["sources"]["protomaps"]["attribution"]


def test_vendor_files_present():
    for name in ("maplibre-gl.js", "maplibre-gl.css", "pmtiles.js"):
        assert (REPO / "web" / "vendor" / name).stat().st_size > 10_000
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Range route** — add to `app.py` (module level helper + route inside `create_app`; `import re`, `from fastapi import Request`, `from fastapi.responses import Response`):
```python
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
BASEMAP_HEADERS = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=86400"}


def range_response(path: Path, range_header: str | None, method: str) -> Response:
    """Byte-range file serving for the pmtiles protocol (it reads by range)."""
    size = path.stat().st_size
    if not range_header:
        if method == "HEAD":
            return Response(headers={**BASEMAP_HEADERS, "Content-Length": str(size)},
                            media_type="application/octet-stream")
        return FileResponse(path, media_type="application/octet-stream", headers=BASEMAP_HEADERS)
    m = _RANGE_RE.match(range_header.strip())
    start = end = None
    if m and (m[1] or m[2]):
        if m[1]:
            start = int(m[1])
            end = min(int(m[2]), size - 1) if m[2] else size - 1
        else:
            start, end = max(0, size - int(m[2])), size - 1
    if start is None or start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with path.open("rb") as f:
        f.seek(start)
        body = f.read(end - start + 1)
    return Response(body, status_code=206, media_type="application/octet-stream",
                    headers={**BASEMAP_HEADERS, "Content-Range": f"bytes {start}-{end}/{size}"})
```
```python
    @app.api_route("/basemap.pmtiles", methods=["GET", "HEAD"])
    def basemap(request: Request):
        path = data_dir / "basemap.pmtiles"
        if not path.is_file():
            return JSONResponse({"error": "basemap not built; run tools/build_basemap.sh"}, status_code=404)
        return range_response(path, request.headers.get("range"), request.method)
```
(A sync `def` route so file reads run in the threadpool.)

- [ ] **Step 4: Vendor libraries.** Download with `curl -fL`:
  - `https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js` → `web/vendor/maplibre-gl.js`
  - `https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css` → `web/vendor/maplibre-gl.css`
  - `https://unpkg.com/pmtiles@3.2.1/dist/pmtiles.js` → `web/vendor/pmtiles.js`
  Verify: `maplibre-gl.js` contains `maplibregl`; `pmtiles.js` defines a global `pmtiles` with `Protocol` (`grep -c "Protocol" web/vendor/pmtiles.js`). If the pmtiles path 404s, list `https://unpkg.com/pmtiles@3.2.1/dist/` and pick the UMD/IIFE build (not `.mjs`/`.cjs`). `web/vendor/LICENSES.txt`: MapLibre GL JS 4.7.1 (BSD-3-Clause), pmtiles 3.2.1 (BSD-3-Clause), with their repo URLs.
  The `test_no_remote_urls_in_pages` test only scans `web/*.{html,css,js}`, not `web/vendor/`, so vendor bundles' embedded URLs are fine.

- [ ] **Step 5: `web/style.json`** (Protomaps basemap v4 tile schema: layers `earth`, `landuse`, `water`, `buildings`, `roads` with `kind` in `highway|major_road|minor_road|path|other`):
```json
{
  "version": 8,
  "name": "Board navy",
  "sources": {
    "protomaps": {
      "type": "vector",
      "url": "pmtiles://basemap.pmtiles",
      "attribution": "© OpenStreetMap contributors"
    }
  },
  "layers": [
    {"id": "background", "type": "background", "paint": {"background-color": "#0f151d"}},
    {"id": "earth", "type": "fill", "source": "protomaps", "source-layer": "earth",
     "paint": {"fill-color": "#0f151d"}},
    {"id": "landuse", "type": "fill", "source": "protomaps", "source-layer": "landuse",
     "paint": {"fill-color": "#151e29"}},
    {"id": "water", "type": "fill", "source": "protomaps", "source-layer": "water",
     "paint": {"fill-color": "#0c2742"}},
    {"id": "buildings", "type": "fill", "source": "protomaps", "source-layer": "buildings", "minzoom": 14,
     "paint": {"fill-color": "#151e29"}},
    {"id": "roads-minor", "type": "line", "source": "protomaps", "source-layer": "roads",
     "filter": ["in", ["get", "kind"], ["literal", ["minor_road", "other"]]],
     "layout": {"line-cap": "round", "line-join": "round"},
     "paint": {"line-color": "#24324a",
               "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 11, 0.3, 13, 0.9, 16, 4]}},
    {"id": "roads-major", "type": "line", "source": "protomaps", "source-layer": "roads",
     "filter": ["in", ["get", "kind"], ["literal", ["major_road", "highway"]]],
     "layout": {"line-cap": "round", "line-join": "round"},
     "paint": {"line-color": "#33465f",
               "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 0.5, 12, 1.4, 16, 7]}}
  ]
}
```

- [ ] **Step 6: `tools/build_basemap.sh`**
```bash
#!/usr/bin/env bash
# One-time (or occasional) basemap build: cut the Metrorail area out of the
# Protomaps daily planet build into data/basemap.pmtiles. OpenStreetMap data,
# ODbL -- the page shows "© OpenStreetMap contributors".
#
#   tools/build_basemap.sh            # latest build
#   tools/build_basemap.sh 20261019   # a specific build date
#
# The bbox covers the whole system (Ashburn to Largo, Shady Grove to
# Franconia) so the phone can zoom out; maxzoom 15 is plenty for a wall map.
set -euo pipefail
cd "$(dirname "$0")/.."

PMTILES_VERSION="1.28.0"
BBOX="-77.52,38.74,-76.82,39.14"   # west,south,east,north
MAXZOOM=15

case "$(uname -m)" in
  aarch64|arm64) ARCH=arm64 ;;
  x86_64) ARCH=x86_64 ;;
  *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

mkdir -p data/bin
if [ ! -x data/bin/pmtiles ]; then
  curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_${ARCH}.tar.gz" \
    | tar -xz -C data/bin pmtiles
fi

if [ $# -ge 1 ]; then
  BUILD="$1"
else
  BUILD="$(curl -fsSL https://build-metadata.protomaps.dev/builds.json \
    | python3 -c 'import json,sys; print(sorted(b["key"] for b in json.load(sys.stdin))[-1].removesuffix(".pmtiles"))')"
fi
echo "extracting from Protomaps build ${BUILD} (bbox ${BBOX}, maxzoom ${MAXZOOM})"
data/bin/pmtiles extract "https://build.protomaps.com/${BUILD}.pmtiles" data/basemap.pmtiles.tmp \
  --bbox="${BBOX}" --maxzoom="${MAXZOOM}"
mv data/basemap.pmtiles.tmp data/basemap.pmtiles
ls -lh data/basemap.pmtiles
```
`chmod +x` it (and `git update-index --chmod=+x tools/build_basemap.sh` since the dev PC is Windows). Before relying on the constants, confirm with WebFetch that go-pmtiles v1.28.0 has `go-pmtiles_1.28.0_Linux_arm64.tar.gz` (else use the latest release's asset name) and that `https://build-metadata.protomaps.dev/builds.json` returns objects with a `key` like `20261019.pmtiles`; correct the script if either differs.

- [ ] **Step 7: Run** `.venv/Scripts/python -m pytest -q` → PASS.

- [ ] **Step 8: Build the basemap on the Pi.** `git push`, then on the Pi: `cd ~/wmata-board && git pull --ff-only && tools/build_basemap.sh` (expect tens of MB; takes minutes). Run it in the background with output to `data/build_basemap.log` if it is slow. Then on the Pi: `.venv/bin/python -m wmata_board --help` sanity, and `curl -sI -H "Range: bytes=0-126" localhost:8766/basemap.pmtiles` after a service restart → 206. For local dev, copy the built file down: `scp raspberrypi:wmata-board/data/basemap.pmtiles data/`.

- [ ] **Step 9: Commit** `git add tools/build_basemap.sh web/style.json web/vendor src tests && git commit -m "Self-hosted Protomaps basemap: build tool, Board-navy style, range serving"`

---

### Task 14: Track geometry and glide (pure JS)

**Files:**
- Create: `web/track.js`, `tests/js/track.test.js`

**Interfaces:**
- Produces (ES module):
  - `mercator(lon, lat) -> [x, y]` (world units 0..1, y down); `unmercator(x, y) -> [lon, lat]`
  - `coverView([w, s, e, n], width, height, tileSize = 512) -> {center: [lon, lat], zoom}` — the bbox covers the panel (like CSS `cover`)
  - `buildTrack(lonlats) -> {pts: [[x,y]...], cum: [...], length}` (mercator)
  - `snapToTrack(track, [x, y]) -> {s, dist}`
  - `pointAt(track, s) -> {x, y, dx, dy}` (unit tangent; s clamped)
  - `laneOffset(points, off) -> points` (screen-space perpendicular offset, sign convention `(x - dy/L*off, y + dx/L*off)`)
  - `headingSign(track, s, bearingDeg) -> -1 | 0 | 1`
  - `kmToMerc(km, lat = 38.9)`; `JUMP_MERC = kmToMerc(1)`
  - `class Glider({jump = JUMP_MERC, fadeMs = 1500, minMs = 1000, maxMs = 15000})`: `update(vehicles: [{id, line, s, dir}], feedTs: number, nowMs)`, `at(nowMs) -> [{id, line, s, dir, opacity}]`.

- [ ] **Step 1: Failing tests** — `tests/js/track.test.js`:
```js
import test from "node:test";
import assert from "node:assert/strict";
import { mercator, unmercator, coverView, buildTrack, snapToTrack, pointAt, laneOffset,
         headingSign, kmToMerc, Glider } from "../../web/track.js";

const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);

test("mercator round trip", () => {
  const [x, y] = mercator(-77.08, 38.89);
  const [lon, lat] = unmercator(x, y);
  near(lon, -77.08, 1e-9); near(lat, 38.89, 1e-9);
  near(mercator(0, 0)[0], 0.5); near(mercator(0, 0)[1], 0.5);
});

test("coverView covers the panel", () => {
  const bbox = [-77.122, 38.844, -76.978, 38.966];
  const v = coverView(bbox, 883, 957);
  const [x0, y0] = mercator(bbox[0], bbox[3]), [x1, y1] = mercator(bbox[2], bbox[1]);
  const px = 512 * 2 ** v.zoom;
  assert.ok((x1 - x0) * px >= 883 - 1e-6 && (y1 - y0) * px >= 957 - 1e-6);
  assert.ok(Math.abs((x1 - x0) * px - 883) < 1e-6 || Math.abs((y1 - y0) * px - 957) < 1e-6);
  near(v.center[0], -77.05, 1e-9);
});

const line = buildTrack([[-77.1, 38.9], [-77.0, 38.9], [-77.0, 39.0]]);

test("buildTrack arc length", () => {
  assert.equal(line.pts.length, 3);
  near(line.cum[0], 0);
  near(line.length, line.cum[2]);
  assert.ok(line.cum[1] > 0 && line.cum[2] > line.cum[1]);
});

test("snap and pointAt are inverse along the track", () => {
  const p = pointAt(line, line.cum[1] / 2);
  const { s, dist } = snapToTrack(line, [p.x, p.y + 1e-6]);
  near(s, line.cum[1] / 2, 1e-9);
  assert.ok(dist < 2e-6);
  near(p.dx, 1); near(p.dy, 0);
  const end = pointAt(line, 99);
  near(end.x, line.pts[2][0]); near(end.y, line.pts[2][1]);
  const start = pointAt(line, -5);
  near(start.x, line.pts[0][0]);
});

test("laneOffset shifts perpendicular", () => {
  const out = laneOffset([[0, 0], [10, 0]], 3);
  assert.deepEqual(out, [[0, 3], [10, 3]]);
  assert.deepEqual(laneOffset([[0, 0], [10, 0]], 0), [[0, 0], [10, 0]]);
});

test("headingSign from bearing vs track direction (track runs east here)", () => {
  const s = line.cum[1] / 2;
  assert.equal(headingSign(line, s, 90), 1);     // heading east = along the track
  assert.equal(headingSign(line, s, 270), -1);
  assert.equal(headingSign(line, s, 0), 0);      // perpendicular: unknown
  assert.equal(headingSign(line, s, null), 0);
});

test("glider interpolates between snapshots over the feed interval", () => {
  const g = new Glider({ fadeMs: 1000 });
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 100, 0);
  assert.equal(g.at(0)[0].s, 0.00001);
  assert.equal(g.at(0)[0].opacity, 1);                 // first snapshot shows at once
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 105, 10_000);   // < 1 km: glides
  near(g.at(10_000)[0].s, 0.00001);
  near(g.at(12_500)[0].s, 0.000015);
  near(g.at(20_000)[0].s, 0.00002);
});

test("glider continues from where it is drawn when a snapshot lands mid-glide", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 110, 0);   // 10 s glide
  g.update([{ id: "a", line: "OR", s: 0.00003, dir: 1 }], 115, 5000); // mid-way: drawn at 0.00001
  near(g.at(5000)[0].s, 0.00001);
  near(g.at(10_000)[0].s, 0.00003);
});

test("repeated feed timestamp is ignored (review focus 4)", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 105, 1000);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 105, 3000);   // same snapshot again
  near(g.at(3500)[0].s, 0.00001 * 0.5);
});

test("timestamp going backwards (fixture wrap) snaps instead of gliding", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 200, 0);
  g.update([{ id: "a", line: "OR", s: 0.0, dir: 1 }], 100, 1000);
  near(g.at(1000)[0].s, 0.0);
});

test("jumps over ~1 km and line changes snap", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }, { id: "b", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: kmToMerc(3), dir: 1 }, { id: "b", line: "SV", s: 0.00001, dir: 1 }], 105, 1000);
  near(g.at(1000).find(v => v.id === "a").s, kmToMerc(3));
  const b = g.at(1000).find(v => v.id === "b");
  assert.equal(b.line, "SV"); near(b.s, 0.00001);
});

test("vehicles that vanish fade out, new ones fade in", () => {
  const g = new Glider({ fadeMs: 1000 });
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "b", line: "OR", s: 0, dir: 1 }], 105, 1000);
  const a = g.at(1500).find(v => v.id === "a"), b = g.at(1500).find(v => v.id === "b");
  near(a.opacity, 0.5); near(b.opacity, 0.5);
  assert.equal(g.at(2100).find(v => v.id === "a"), undefined);
});

test("direction falls back to movement, then to the last known", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 0 }], 100, 0);
  assert.equal(g.at(0)[0].dir, 1);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 0 }], 105, 1000);
  assert.equal(g.at(1000)[0].dir, -1);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 0 }], 110, 2000);
  assert.equal(g.at(2000)[0].dir, -1);
});
```

- [ ] **Step 2: Run** `node --test tests/js/` → FAIL.

- [ ] **Step 3: Implement `web/track.js`**
```js
// Track geometry and train gliding. Pure (no DOM, no MapLibre) so node can
// test it. Positions along a line are arc lengths `s` in Web Mercator world
// units (0..1), which don't change with zoom -- the phone can pan and pinch
// mid-glide and nothing jumps.

export const TILE = 512;

export function mercator(lon, lat) {
  const sin = Math.sin(lat * Math.PI / 180);
  return [(lon + 180) / 360, 0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)];
}

export function unmercator(x, y) {
  return [x * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI];
}

export function kmToMerc(km, lat = 38.9) {
  return km / (40075.017 * Math.cos(lat * Math.PI / 180));
}
export const JUMP_MERC = kmToMerc(1);

// Center + zoom at which the bbox COVERS a width x height panel.
export function coverView([w, s, e, n], width, height, tileSize = TILE) {
  const [x0, y0] = mercator(w, n), [x1, y1] = mercator(e, s);
  const scale = Math.max(width / (x1 - x0), height / (y1 - y0));
  return { center: unmercator((x0 + x1) / 2, (y0 + y1) / 2), zoom: Math.log2(scale / tileSize) };
}

export function buildTrack(lonlats) {
  const pts = lonlats.map(([lon, lat]) => mercator(lon, lat));
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  }
  return { pts, cum, length: cum[cum.length - 1] };
}

export function snapToTrack(track, [px, py]) {
  const { pts, cum } = track;
  let best = 0, bestD = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-30;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
    const qx = ax + t * dx, qy = ay + t * dy, d = (qx - px) ** 2 + (qy - py) ** 2;
    if (d < bestD) { bestD = d; best = cum[i] + t * Math.sqrt(l2); }
  }
  return { s: best, dist: Math.sqrt(bestD) };
}

export function pointAt(track, s) {
  const { pts, cum, length } = track;
  s = Math.max(0, Math.min(length, s));
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] <= s) lo = m; else hi = m; }
  const [ax, ay] = pts[lo], [bx, by] = pts[hi];
  const seg = (cum[hi] - cum[lo]) || 1e-30, t = (s - cum[lo]) / seg;
  const len = Math.hypot(bx - ax, by - ay) || 1e-30;
  return { x: ax + (bx - ax) * t, y: ay + (by - ay) * t, dx: (bx - ax) / len, dy: (by - ay) / len };
}

// Parallel lanes for shared track, in screen pixels.
export function laneOffset(points, off) {
  if (!off) return points.map(p => [p[0], p[1]]);
  return points.map(([x, y], i) => {
    const a = points[Math.max(i - 1, 0)], b = points[Math.min(i + 1, points.length - 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
    return [x - dy / l * off, y + dx / l * off];
  });
}

// +1 if the bearing points along increasing s, -1 against, 0 if unclear.
export function headingSign(track, s, bearingDeg) {
  if (bearingDeg === null || bearingDeg === undefined) return 0;
  const { dx, dy } = pointAt(track, s);
  const b = bearingDeg * Math.PI / 180;
  const d = dx * Math.sin(b) + dy * -Math.cos(b);    // mercator y points south
  return d > 0.3 ? 1 : d < -0.3 ? -1 : 0;
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Keeps the previous and latest snapshot per vehicle and animates between them
// over the measured interval between snapshots -- ~one interval behind real
// time, but smooth.
export class Glider {
  constructor({ jump = JUMP_MERC, fadeMs = 1500, minMs = 1000, maxMs = 15000 } = {}) {
    Object.assign(this, { jump, fadeMs, minMs, maxMs });
    this.v = new Map();
    this.lastTs = null;
  }

  _s(e, nowMs) {
    if (!e.dur) return e.to;
    return e.from + (e.to - e.from) * clamp((nowMs - e.t0) / e.dur, 0, 1);
  }

  update(vehicles, feedTs, nowMs) {
    if (feedTs === this.lastTs) return;
    const first = this.lastTs === null;
    const backwards = !first && feedTs < this.lastTs;
    const dur = first || backwards ? 0 : clamp((feedTs - this.lastTs) * 1000, this.minMs, this.maxMs);
    this.lastTs = feedTs;
    const seen = new Set();
    for (const nv of vehicles) {
      seen.add(nv.id);
      const old = this.v.get(nv.id);
      const same = old && !old.leaving && old.line === nv.line;
      const cur = same ? this._s(old, nowMs) : nv.s;
      const glide = same && dur > 0 && Math.abs(nv.s - cur) <= this.jump;
      const from = glide ? cur : nv.s;
      const moved = Math.sign(nv.s - (same ? cur : nv.s));
      const dir = nv.dir || moved || (same ? old.dir : 0) || 1;
      this.v.set(nv.id, {
        id: nv.id, line: nv.line, from, to: nv.s, t0: nowMs, dur: glide ? dur : 0, dir,
        born: same ? old.born : (first ? nowMs - this.fadeMs : nowMs), leaving: null,
      });
    }
    for (const e of this.v.values()) {
      if (!seen.has(e.id) && !e.leaving) {
        e.from = e.to = this._s(e, nowMs);
        e.dur = 0;
        e.leaving = nowMs;
      }
    }
  }

  at(nowMs) {
    const out = [];
    for (const [id, e] of this.v) {
      let opacity;
      if (e.leaving !== null) {
        opacity = 1 - (nowMs - e.leaving) / this.fadeMs;
        if (opacity <= 0) { this.v.delete(id); continue; }
      } else {
        opacity = clamp((nowMs - e.born) / this.fadeMs, 0, 1);
      }
      out.push({ id, line: e.line, s: this._s(e, nowMs), dir: e.dir, opacity });
    }
    return out;
  }
}
```
Check against the tests: in "repeated feed timestamp", the second update starts a 5 s glide at t=1000 from 0 → 0.00001; at 3500 it is half-way (`0.000005`) and the duplicate at 3000 changed nothing. In "direction falls back", first update has `dir: 0`, `same` false → `moved` 0 → `dir` 1.

- [ ] **Step 4: Run** `node --test tests/js/` → PASS. **Step 5: Commit** `git add web/track.js tests/js/track.test.js && git commit -m "Track snapping, lanes and train glide (pure JS)"`

---

### Task 15: Map overlay on the wall board

**Files:**
- Create: `web/map.js`
- Modify: `web/index.html` (vendor scripts/CSS), `web/board.js` (create map), `web/board.css` (map styles)

**Interfaces:**
- Consumes: `/api/network`, `/api/positions`, `/basemap.pmtiles`, `/static/style.json`; `track.js`; `format.js` `LINE_COLORS`, `LINE_LETTER`; globals `maplibregl`, `pmtiles`.
- Produces: `map.js` `createMap(el, {interactive = false, fit = "cover"}) -> Promise<{map, recenter(), destroy()}>` — `fit: "cover"` (wall) keeps the bbox covering the panel on every resize; `fit: "contain"` (phone) starts with `fitBounds(bbox)` and only refits on `recenter()`.

- [ ] **Step 1: Implement `web/map.js`**
```js
// Shared map: MapLibre draws only the Board-navy basemap; an SVG overlay on
// top draws lanes, stations, labels, landmarks and gliding trains, re-projected
// with map.project() on every move so the wall and the phone share this file.
import { LINE_COLORS, LINE_LETTER, escapeHtml } from "./format.js";
import { buildTrack, snapToTrack, pointAt, laneOffset, headingSign, coverView,
         mercator, unmercator, Glider } from "./track.js";

const NS = "http://www.w3.org/2000/svg";
const LW = 7;
const LANE = { RD: 0, OR: -0.5, SV: 0.5, BL: 1.5, GR: -0.5, YL: 0.5 };
const ORDER = ["RD", "GR", "YL", "BL", "OR", "SV"];
const DARK_TEXT = new Set(["OR", "SV", "YL"]);
const LAND = "#0f151d";
const POSITIONS_MS = 5000;
// Hand-tuned label placement from the approved prototype: [dx, dy, anchor, name].
const LABEL_HINTS = {
  K04: [0, 30, "middle", "Ballston"], K02: [0, 30, "middle"], C05: [16, -12, "start"],
  C04: [0, -18, "middle", "Foggy Bottom"], C01: [-16, 28, "end", "Metro Center"],
  D03: [16, 28, "start", "L'Enfant Plaza"], B03: [0, 30, "middle", "Union Station"],
  A03: [-16, -4, "end", "Dupont Circle"], C07: [16, 6, "start", "Pentagon"],
  F05: [14, 22, "start", "Navy Yard"], B05: [-16, 5, "end", "Brookland"],
};

const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};

async function getJson(url) {
  for (let delay = 1000; ; delay = Math.min(delay * 2, 30000)) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) return await r.json();
    } catch (err) { /* retry */ }
    await new Promise(res => setTimeout(res, delay));
  }
}

async function loadStyle() {
  const style = await getJson("/static/style.json");
  let haveBasemap = false;
  try { haveBasemap = (await fetch("/basemap.pmtiles", { method: "HEAD" })).ok; } catch (err) { /* offline */ }
  if (haveBasemap) {
    style.sources.protomaps.url = `pmtiles://${location.origin}/basemap.pmtiles`;
  } else {
    // Review focus 5: no basemap yet -> keep the land-colored background only.
    console.warn("basemap.pmtiles missing; drawing the overlay on plain land");
    delete style.sources.protomaps;
    style.layers = style.layers.filter(l => l.type === "background");
  }
  return style;
}

function badge(line) {
  const c = (LINE_COLORS[line] || ["#888"])[0];
  return `<circle r="16" fill="url(#glow-${line})"/>` +
    `<circle r="10.5" fill="${c}" stroke="#fff" stroke-width="2"/>` +
    `<text y="4.6" text-anchor="middle" font-family="Inter, sans-serif" font-weight="800" font-size="13" ` +
    `fill="${DARK_TEXT.has(line) ? "#111" : "#fff"}">${LINE_LETTER[line] || "?"}</text>` +
    `<path class="dir" d="M15,-4 L21,0 L15,4 Z" fill="#fff"/>`;
}

export async function createMap(el, { interactive = false, fit = "cover" } = {}) {
  const [net, style] = await Promise.all([getJson("/api/network"), loadStyle()]);
  if (!window.__pmtilesProtocol) {
    window.__pmtilesProtocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", window.__pmtilesProtocol.tile);
  }
  const [w, s, e, n] = net.view.bbox;
  const start = fit === "cover" ? coverView(net.view.bbox, el.clientWidth, el.clientHeight) : null;
  const map = new maplibregl.Map({
    container: el, style, interactive, attributionControl: false, fadeDuration: 0,
    ...(start ? { center: start.center, zoom: start.zoom } : { bounds: [[w, s], [e, n]] }),
    dragRotate: false, pitchWithRotate: false, touchPitch: false,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");
  if (interactive) map.touchZoomRotate.disableRotation();

  const tracks = Object.fromEntries(Object.entries(net.lines).map(([k, v]) => [k, buildTrack(v)]));
  const home = net.stations.find(st => st.codes.includes(net.home));

  // ---- SVG overlay ----
  const svg = svgEl("svg", { class: "overlay" });
  svg.innerHTML = `<defs>${ORDER.map(l => `<radialGradient id="glow-${l}">` +
    `<stop offset="0" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0.7"/>` +
    `<stop offset="0.45" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0.28"/>` +
    `<stop offset="1" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0"/></radialGradient>`).join("")}` +
    `<radialGradient id="hosp"><stop offset="0" stop-color="#ff8a9b" stop-opacity=".55"/>` +
    `<stop offset="1" stop-color="#ff8a9b" stop-opacity="0"/></radialGradient></defs>` +
    `<g class="static"></g><g class="trains"></g>` +
    `<text class="live" x="24" y="44"><tspan fill="#3ddc84">●</tspan> LIVE · <tspan class="count">0</tspan> TRAINS</text>`;
  el.appendChild(svg);
  const pulse = document.createElement("div");
  pulse.className = "pulse";
  el.appendChild(pulse);
  const gStatic = svg.querySelector(".static"), gTrains = svg.querySelector(".trains");
  const countEl = svg.querySelector(".count");

  const project = (lon, lat) => { const p = map.project([lon, lat]); return [p.x, p.y]; };
  const pl = pts => pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");

  function drawStatic() {
    const W = el.clientWidth, H = el.clientHeight, out = [];
    for (const p of net.places) {
      const [x, y] = project(p.lon, p.lat);
      out.push(`<text class="place" x="${x.toFixed(0)}" y="${y.toFixed(0)}" text-anchor="middle">${escapeHtml(p.name)}</text>`);
    }
    const lanes = ORDER.filter(l => net.lines[l]).map(l =>
      [l, laneOffset(net.lines[l].map(([lon, lat]) => project(lon, lat)), LANE[l] * LW)]);
    out.push(`<g fill="none" stroke-linecap="round" stroke-linejoin="round">`);
    for (const [, pts] of lanes) out.push(`<polyline points="${pl(pts)}" stroke="#0a0e14" stroke-width="${LW + 5}"/>`);
    for (const [l, pts] of lanes) out.push(`<polyline points="${pl(pts)}" stroke="${LINE_COLORS[l][0]}" stroke-width="${LW}"/>`);
    out.push(`</g>`);
    for (const st of net.stations) {
      if (st === home) continue;
      const [x, y] = project(st.lon, st.lat);
      if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${st.transfer ? 6.2 : 3.8}" fill="${LAND}" ` +
               `stroke="#cfd8e3" stroke-width="${st.transfer ? 2.6 : 2}"/>`);
    }
    out.push(`<g class="labels">`);
    for (const code of net.labels) {
      const st = net.stations.find(x => x.codes.includes(code));
      if (!st) continue;
      const [dx, dy, anchor, name] = LABEL_HINTS[code] || [0, 26, "middle"];
      const [x, y] = project(st.lon, st.lat);
      out.push(`<text x="${(x + dx).toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}">${escapeHtml((name || st.name).toUpperCase())}</text>`);
    }
    out.push(`</g>`);
    for (const lm of net.landmarks) {
      const [x, y] = project(lm.lon, lm.lat);
      const [first, ...rest] = lm.name.toUpperCase().split(" ");
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="26" fill="url(#hosp)"/>` +
        `<rect x="${(x - 11).toFixed(1)}" y="${(y - 11).toFixed(1)}" width="22" height="22" rx="6" fill="#ff8a9b" stroke="${LAND}" stroke-width="2.5"/>` +
        `<path d="M${x.toFixed(1)},${(y - 6).toFixed(1)} V${(y + 6).toFixed(1)} M${(x - 6).toFixed(1)},${y.toFixed(1)} H${(x + 6).toFixed(1)}" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/>` +
        `<g class="landmark"><text x="${x.toFixed(1)}" y="${(y + 31).toFixed(1)}">${escapeHtml(first)}</text>` +
        (rest.length ? `<text x="${x.toFixed(1)}" y="${(y + 47).toFixed(1)}">${escapeHtml(rest.join(" "))}</text>` : "") + `</g>`);
    }
    if (home) {
      const [x, y] = project(home.lon, home.lat);
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="10" fill="${LAND}" stroke="#fff" stroke-width="3.5"/>` +
        `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="#fff"/>` +
        `<text class="home" x="${(x - 18).toFixed(1)}" y="${(y - 22).toFixed(1)}" text-anchor="end">${escapeHtml(home.name.toUpperCase())}</text>`);
      pulse.style.left = `${x}px`;
      pulse.style.top = `${y}px`;
    }
    gStatic.innerHTML = out.join("");
  }

  // ---- trains ----
  const glider = new Glider();
  const els = new Map();
  let stale = true;

  async function pollPositions() {
    try {
      const r = await fetch("/api/positions", { cache: "no-store" });
      if (r.ok) {
        const body = await r.json();
        stale = body.stale;
        gTrains.classList.toggle("faded", stale);
        if (body.feed_timestamp !== null) {
          const vs = [];
          for (const v of body.vehicles) {
            const track = tracks[v.line];
            if (!track) continue;
            const { s } = snapToTrack(track, mercator(v.lon, v.lat));
            vs.push({ id: v.id, line: v.line, s, dir: headingSign(track, s, v.heading) });
          }
          glider.update(vs, body.feed_timestamp, performance.now());
        }
      }
    } catch (err) { /* keep gliding what we have; fades when stale */ }
    setTimeout(pollPositions, POSITIONS_MS);
  }

  function screenAt(line, s) {
    const track = tracks[line];
    const p = pointAt(track, s), q = pointAt(track, s + 1e-7);
    const [x, y] = project(...unmercator(p.x, p.y));
    let [x2, y2] = project(...unmercator(q.x, q.y));
    if (Math.hypot(x2 - x, y2 - y) < 1e-6) { x2 = x + p.dx; y2 = y + p.dy; }
    const dx = x2 - x, dy = y2 - y, l = Math.hypot(dx, dy) || 1;
    const off = LANE[line] * LW;
    return [x - dy / l * off, y + dx / l * off, Math.atan2(dy, dx)];
  }

  let lastFrame = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - lastFrame < 33) return;           // ~30 fps is plenty, and kind to the Pi
    lastFrame = now;
    const W = el.clientWidth, H = el.clientHeight, seen = new Set();
    let visible = 0;
    for (const v of glider.at(now)) {
      let e = els.get(v.id);
      if (!e || e.line !== v.line) {
        e?.g.remove();
        const g = svgEl("g");
        g.innerHTML = badge(v.line);
        gTrains.appendChild(g);
        e = { g, dir: g.querySelector(".dir"), line: v.line };
        els.set(v.id, e);
      }
      const [x, y, ang] = screenAt(v.line, v.s);
      const deg = ang * 180 / Math.PI + (v.dir < 0 ? 180 : 0);
      e.g.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`);
      e.dir.setAttribute("transform", `rotate(${deg.toFixed(0)})`);
      e.g.style.opacity = v.opacity.toFixed(2);
      if (x > 0 && y > 0 && x < W && y < H && v.opacity > 0.5) visible++;
      seen.add(v.id);
    }
    for (const [id, e] of els) if (!seen.has(id)) { e.g.remove(); els.delete(id); }
    countEl.textContent = stale ? "0" : String(visible);
  }

  function refit() {
    if (fit !== "cover") return;
    const v = coverView(net.view.bbox, el.clientWidth, el.clientHeight);
    map.jumpTo({ center: v.center, zoom: v.zoom });
  }
  const ro = new ResizeObserver(() => { map.resize(); refit(); drawStatic(); });
  ro.observe(el);
  map.on("move", drawStatic);
  map.on("load", drawStatic);
  drawStatic();
  pollPositions();
  requestAnimationFrame(frame);

  return {
    map,
    recenter() {
      if (fit === "cover") refit();
      else map.fitBounds([[w, s], [e, n]], { duration: 600 });
    },
    destroy() { ro.disconnect(); map.remove(); },
  };
}
```

- [ ] **Step 2: Wire into the wall.** `web/index.html` head: add `<link rel="stylesheet" href="/static/vendor/maplibre-gl.css">` before `board.css`; before the module script add `<script src="/static/vendor/maplibre-gl.js"></script>` and `<script src="/static/vendor/pmtiles.js"></script>`. In `web/board.js` add `import { createMap } from "./map.js";` and at the end: `createMap($("map"), { interactive: false, fit: "cover" }).catch(err => console.error("map failed", err));`.

Note: the stage is CSS-scaled; `el.clientWidth/Height` are the unscaled 1920×1080-space sizes, which is what MapLibre and the SVG both use — consistent. On the Pi (1920×1080 display) the scale is 1.

Append to `web/board.css`:
```css
.mapbox .maplibregl-map { position: absolute; inset: 0; }
.overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: hidden;
           font-family: Inter, Helvetica, Arial, sans-serif; }
.overlay .place { font-size: 17px; font-weight: 800; letter-spacing: 7px; fill: #3b4a5e; }
.overlay .labels text { font-size: 13px; font-weight: 700; fill: #a9b8c9; letter-spacing: 1.6px;
                        paint-order: stroke; stroke: #0f151d; stroke-width: 5px; stroke-linejoin: round; }
.overlay .landmark text { font-size: 13px; font-weight: 800; fill: #f7c3cc; letter-spacing: 1.6px; text-anchor: middle;
                          paint-order: stroke; stroke: #0f151d; stroke-width: 5px; stroke-linejoin: round; }
.overlay .home { font-size: 16px; font-weight: 800; letter-spacing: 2.2px; fill: #fff;
                 paint-order: stroke; stroke: #0f151d; stroke-width: 5px; }
.overlay .live { font-size: 18px; font-weight: 800; letter-spacing: 5px; fill: #8b95a3;
                 paint-order: stroke; stroke: #0f151d; stroke-width: 5px; }
.overlay .trains { transition: opacity 2s; }
.overlay .trains.faded { opacity: 0; }
.pulse { position: absolute; width: 20px; height: 20px; margin: -10px 0 0 -10px; border: 3px solid #fff;
         border-radius: 50%; animation: pulse 2.4s ease-out infinite; pointer-events: none; }
@keyframes pulse { from { transform: scale(1); opacity: .85; } to { transform: scale(3.2); opacity: 0; } }
.maplibregl-ctrl-attrib { background: transparent !important; font: 11px Inter, sans-serif; }
.maplibregl-ctrl-attrib a { color: #4d5866 !important; }
```

- [ ] **Step 3: Tests still pass**: `.venv/Scripts/python -m pytest -q && node --test tests/js/` (asset test checks `/static/vendor/...` refs exist).

- [ ] **Step 4: Browser check (fixtures, local).** With `data/basemap.pmtiles` copied from the Pi (Task 13 step 8) run fixtures mode, open `/` at 1920×1080 and screenshot: navy basemap with streets and the Potomac; OR/SV parallel lanes through Rosslyn; Court House ring with pulse; labels; Children's National badge; badge markers moving smoothly (check two screenshots 3 s apart differ slightly); `LIVE · N TRAINS` with N > 0. Then rename `data/basemap.pmtiles` temporarily, reload: overlay still renders on plain land, no console errors besides the warning (read console via claude-in-chrome). Compare against `.superpowers/prototypes/board-replay.html` ("Line badge" style) side by side for visual parity; fix glaring differences.

- [ ] **Step 5: Commit + deploy.** `git add web && git commit -m "Live map: basemap, track overlay, gliding train badges"`, push, Pi: `git pull --ff-only && .venv/bin/pip install -q -e . && systemctl --user restart wmata-board`. Verify `curl -s localhost:8766/api/network | head -c 200` and `curl -s localhost:8766/api/positions | head -c 300` on the Pi (live data). Repeat the Task 10 step 8 wall check (switch, inspect, switch back), this time also evaluating `document.querySelectorAll('.trains g').length` via CDP.

---

# Milestone 6 — Phone view

### Task 16: Phone page + Tailscale mapping

**Files:**
- Create: `web/phone.html`, `web/phone.css`, `web/phone.js`
- Modify: `src/wmata_board/app.py` (`/phone` route), `tests/test_app.py`, `README.md` (phone section)

**Interfaces:**
- Consumes: `createMap(el, {interactive: true, fit: "contain"})`, `arrivalsHtml`, `alertHtml`, `pillState`, `formatClock`.
- Produces: `GET /phone`.

- [ ] **Step 1: Failing test** — append to `tests/test_app.py`:
```python
def test_phone_served(app):
    with TestClient(app) as c:
        r = c.get("/phone")
    assert r.status_code == 200 and 'id="sheet"' in r.text
```
- [ ] **Step 2: Run** → FAIL (404). **Step 3: Route** in `app.py`:
```python
    @app.get("/phone")
    async def phone():
        return FileResponse(WEB_DIR / "phone.html", headers=NO_STORE)
```

- [ ] **Step 4: Page.** `web/phone.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Court House</title>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0d1117">
  <link rel="stylesheet" href="/static/vendor/maplibre-gl.css">
  <link rel="stylesheet" href="/static/board.css">
  <link rel="stylesheet" href="/static/phone.css">
</head>
<body class="phone">
  <div id="map" class="phonemap"></div>
  <button id="recenter" class="recenter" aria-label="Recenter map">◎</button>
  <section id="sheet" class="sheet">
    <div class="handle" id="handle"><span></span></div>
    <header class="shdr">
      <span id="station" class="stn">Court House</span>
      <span class="right"><span id="pill" class="pill" hidden></span><span id="clock" class="clk"></span></span>
    </header>
    <div id="alerts" class="palerts"></div>
    <div id="arrivals" class="arr"></div>
  </section>
  <script src="/static/vendor/maplibre-gl.js"></script>
  <script src="/static/vendor/pmtiles.js"></script>
  <script type="module" src="/static/phone.js"></script>
</body>
</html>
```
`web/phone.css` (board.css supplies fonts, rows, chips, overlay styles; here sizes switch from cqw to px for a phone):
```css
body.phone { background: #0d1117; color: #f2f4f7; font-family: Inter, Helvetica, Arial, sans-serif;
             position: fixed; inset: 0; overflow: hidden; touch-action: none; }
body.phone * { box-sizing: border-box; }
.phonemap { position: absolute; inset: 0; background: #0f151d; }
.recenter { position: absolute; right: 14px; top: calc(14px + env(safe-area-inset-top)); width: 44px; height: 44px;
            border-radius: 50%; border: 1px solid #2a313c; background: rgba(13,17,23,.9); color: #e6ebf1;
            font-size: 22px; z-index: 3; }
.sheet { position: absolute; left: 0; right: 0; bottom: 0; height: 85vh; z-index: 4; background: #0d1117;
         border-top: 1px solid #2a313c; border-radius: 16px 16px 0 0; padding: 0 16px env(safe-area-inset-bottom);
         transform: translateY(calc(85vh - 38vh)); transition: transform .25s ease; overflow-y: auto;
         touch-action: pan-y; }
.sheet.dragging { transition: none; }
.handle { display: flex; justify-content: center; padding: 10px 0 6px; touch-action: none; cursor: grab; }
.handle span { width: 40px; height: 5px; border-radius: 3px; background: #3b4a5e; }
.shdr { display: flex; justify-content: space-between; align-items: baseline; padding-bottom: 6px;
        border-bottom: 1px solid #2a313c; }
.phone .stn { font-size: 24px; }
.phone .clk { font-size: 18px; }
.phone .pill { font-size: 12px; padding: 3px 9px; }
.phone .arr { padding: 0; }
.phone .plat h2 { font-size: 12px; letter-spacing: 2px; margin: 14px 0 2px; }
.phone .row { grid-template-columns: 46px 1fr 74px; height: 56px; }
.phone .chip { width: 34px; height: 34px; font-size: 14px; }
.phone .dest { font-size: 20px; }
.phone .cars { font-size: 12px; }
.phone .min { font-size: 26px; }
.phone .min small { font-size: 12px; }
.phone .notice { margin-top: 24px; font-size: 18px; }
.palerts .alert { margin-top: 10px; padding: 10px 12px; border-radius: 10px; gap: 8px; flex-wrap: wrap; }
.palerts .tag { font-size: 11px; padding: 3px 7px; }
.palerts .chip.sm { width: 22px; height: 22px; font-size: 10px; }
.palerts .atext { font-size: 14px; -webkit-line-clamp: unset; display: block; flex-basis: 100%; }
```
`web/phone.js`:
```js
// Phone view: full-screen pannable map + draggable bottom sheet with arrivals
// and every alert (no rotation -- there's room to list them).
import { formatClock, pillState } from "./format.js";
import { arrivalsHtml, alertHtml } from "./render.js";
import { createMap } from "./map.js";

const $ = id => document.getElementById(id);
const startMs = Date.now();
let board = null, lastOkMs = null, version = null;

async function poll() {
  try {
    const r = await fetch("/api/board", { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    board = await r.json();
    lastOkMs = Date.now();
    if (version === null) version = board.version;
    else if (board.version !== version) { location.reload(); return; }
    $("station").textContent = board.station.name;
    $("arrivals").innerHTML = arrivalsHtml(board);
    $("alerts").innerHTML = board.alerts.map(a => `<div class="alert">${alertHtml(a)}</div>`).join("");
  } catch (err) {
    console.warn("board poll failed", err);
  } finally {
    setTimeout(poll, 5000);
  }
}

function tick() {
  const now = Date.now();
  $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
  const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
  const pill = $("pill");
  pill.hidden = p.kind === "hidden";
  pill.className = `pill ${p.kind}`;
  pill.textContent = p.text;
}

// Bottom sheet: drag the handle between "peek" (38vh visible) and "open" (85vh).
const sheet = $("sheet");
const PEEK = () => innerHeight * 0.85 - innerHeight * 0.38;
let offset = PEEK(), dragFrom = null;
const place = y => { offset = Math.max(0, Math.min(PEEK(), y)); sheet.style.transform = `translateY(${offset}px)`; };
$("handle").addEventListener("pointerdown", ev => {
  dragFrom = { y: ev.clientY, offset };
  sheet.classList.add("dragging");
  ev.target.setPointerCapture(ev.pointerId);
});
$("handle").addEventListener("pointermove", ev => { if (dragFrom) place(dragFrom.offset + ev.clientY - dragFrom.y); });
$("handle").addEventListener("pointerup", () => {
  if (!dragFrom) return;
  sheet.classList.remove("dragging");
  place(offset < PEEK() / 2 ? 0 : PEEK());
  dragFrom = null;
});
addEventListener("resize", () => place(offset > 0 ? PEEK() : 0));
place(PEEK());

createMap($("map"), { interactive: true, fit: "contain" })
  .then(m => {
    $("recenter").addEventListener("click", () => m.recenter());
    // Allow zooming out to the whole system, but not off into the void.
    m.map.setMaxBounds([[-77.75, 38.6], [-76.6, 39.3]]);
    m.map.setMinZoom(8.5);
  })
  .catch(err => console.error("map failed", err));

setInterval(tick, 1000);
tick();
poll();
```

- [ ] **Step 5: Run** `.venv/Scripts/python -m pytest -q && node --test tests/js/` → PASS.

- [ ] **Step 6: Browser check (fixtures).** Open `/phone` in Chrome with a 390×844 viewport (resize the window; device emulation isn't required): map fills the screen, starts on the wall's bbox, pans/zooms, recenter works; sheet peeks with arrivals, drags open; alerts listed. Screenshot.

- [ ] **Step 7: Commit, deploy, Tailscale.** Update README's phone section, `git commit`, push, Pi pull + restart. On the Pi: `tailscale serve --bg --https=8446 http://127.0.0.1:8766` then `tailscale serve status` shows the 8446 mapping. From the dev PC: `curl -s https://raspberrypi.tail7b0b4d.ts.net:8446/healthz` → ok, and open `https://raspberrypi.tail7b0b4d.ts.net:8446/phone` in Chrome at phone size for a live screenshot.

---

### Task 17: Final verification

- [ ] Full suite: `.venv/Scripts/python -m pytest -q` and `node --test tests/js/` — all green, output captured.
- [ ] On the Pi: `systemctl --user is-active wmata-board kiosk-selector`, `journalctl --user -u wmata-board --since "1 hour ago" | grep -ci traceback` → 0, `grep -c "$(cut -d= -f2 ~/wmata-board.env)" <(journalctl --user -u wmata-board)` → 0 (key never logged; do not echo the key itself).
- [ ] Demand gating live: leave no page open for 2 minutes, then `curl -s localhost:8766/healthz` shows arrivals `age_s` growing (no polling while idle); request `/api/board` and confirm age resets within ~3 s.
- [ ] Update the spec's Status line to "implemented" with a short progress log of what shipped and any deviations.
- [ ] Whole-branch code review (superpowers:requesting-code-review), fix findings, push.

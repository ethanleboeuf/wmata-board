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
    trips: float = 20.0
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


_DEFAULT_BBOX = (-77.122, 38.844, -76.978, 38.966)
THEMES = ("", "halloween")   # "" is the everyday Board-navy map


@dataclass(frozen=True, slots=True)
class MapConfig:
    bbox: tuple[float, float, float, float] = _DEFAULT_BBOX
    labels: tuple[str, ...] = ()
    places: tuple[Place, ...] = ()
    landmarks: tuple[Landmark, ...] = ()
    theme: str = ""


@dataclass(frozen=True, slots=True)
class CommuteConfig:
    """Children's National via the Brookland shuttle. Times are minutes since
    local midnight; durations are minutes."""
    name: str = "Children's National"
    home: str = "K01"                      # Court House
    transfer: tuple[str, str] = ("C01", "A01")   # Metro Center: OR/SV platform, Red platform
    shuttle_stop: str = "B05"              # Brookland-CUA
    evening_from: str = "B07"              # Takoma, the other evening start
    morning: tuple[int, int] = (390, 490)  # 6:30-8:10
    evening: tuple[int, int] = (960, 1110)  # 4:00-6:30
    shuttles: tuple[int, ...] = (492, 498)  # 8:12, 8:18: highlighted
    shuttle_every: int = 6
    shuttle_ride: float = 10.0
    transfer_walk: float = 2.0
    shuttle_walk: float = 3.0
    rows: int = 5
    wall_platform: str = "2"               # the wall platform the panel replaces
    lines: tuple[str, ...] = ("OR", "SV", "RD")   # alerts for these show with the panel

    @property
    def stations(self) -> tuple[str, ...]:
        return (self.home, *self.transfer, self.shuttle_stop, self.evening_from)


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
    commute: CommuteConfig | None = None
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
    for name in ("arrivals", "incidents", "positions", "trips", "idle_after"):
        if name in t:
            v = _number(t[name], f"[polling].{name}")
            if v <= 0:
                raise ConfigError(f"[polling].{name} must be > 0")
            values[name] = v
    return PollingConfig(**values)


def _map(t: Mapping[str, Any]) -> MapConfig:
    bbox = t.get("bbox", list(_DEFAULT_BBOX))
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

    theme = str(t.get("theme", "")).strip().lower()
    if theme not in THEMES:
        raise ConfigError(f"[map].theme must be one of {', '.join(repr(x) for x in THEMES)}, got {theme!r}")

    return MapConfig((west, south, east, north), tuple(str(x).upper() for x in labels),
                     tuple(places), tuple(landmarks), theme)


_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _hhmm(value: Any, where: str) -> int:
    m = _HHMM_RE.match(str(value).strip())
    if not m:
        raise ConfigError(f"{where}: {value!r} is not a time like '08:12'")
    return int(m[1]) * 60 + int(m[2])


def _window(value: Any, where: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{where} must be [start, end], e.g. [\"06:30\", \"08:10\"]")
    start, end = (_hhmm(v, where) for v in value)
    if start >= end:
        raise ConfigError(f"{where}: start must be before end")
    return start, end


def _code(value: Any, where: str) -> str:
    code = str(value).strip().upper()
    if not _STATION_RE.match(code):
        raise ConfigError(f"{where}: {value!r} is not a station code like 'K01'")
    return code


def _commute(t: Mapping[str, Any]) -> CommuteConfig | None:
    if not t:
        return None
    d = CommuteConfig()
    transfer = t.get("transfer", list(d.transfer))
    if not isinstance(transfer, list) or len(transfer) != 2:
        raise ConfigError("[commute].transfer must be [arriving platform code, departing platform code]")
    minutes = {}
    for name in ("shuttle_ride", "transfer_walk", "shuttle_walk"):
        v = _number(t.get(name, getattr(d, name)), f"[commute].{name}")
        if not 0 <= v <= 60:
            raise ConfigError(f"[commute].{name} must be 0-60 minutes")
        minutes[name] = v
    every = t.get("shuttle_every", d.shuttle_every)
    if isinstance(every, bool) or not isinstance(every, int) or every < 1 or 60 % every:
        raise ConfigError("[commute].shuttle_every must be a whole number of minutes that divides 60")
    rows = t.get("rows", d.rows)
    if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 8:
        raise ConfigError(f"[commute].rows must be an integer 1-8, got {rows!r}")
    lines = t.get("lines", list(d.lines))
    if not isinstance(lines, list) or not lines:
        raise ConfigError("[commute].lines must be a non-empty list of line codes")
    lines = tuple(str(x).strip().upper() for x in lines)
    bad = [x for x in lines if x not in LINE_CODES]
    if bad:
        raise ConfigError(f"[commute].lines: unknown line(s) {', '.join(bad)}")
    shuttles = t.get("shuttles", [])
    if not isinstance(shuttles, list):
        raise ConfigError("[commute].shuttles must be a list of times")
    return CommuteConfig(
        name=str(t.get("name", d.name)),
        home=_code(t.get("home", d.home), "[commute].home"),
        transfer=(_code(transfer[0], "[commute].transfer"), _code(transfer[1], "[commute].transfer")),
        shuttle_stop=_code(t.get("shuttle_stop", d.shuttle_stop), "[commute].shuttle_stop"),
        evening_from=_code(t.get("evening_from", d.evening_from), "[commute].evening_from"),
        morning=_window(t["morning"], "[commute].morning") if "morning" in t else d.morning,
        evening=_window(t["evening"], "[commute].evening") if "evening" in t else d.evening,
        shuttles=tuple(sorted(_hhmm(x, "[commute].shuttles") for x in shuttles)) if "shuttles" in t else d.shuttles,
        shuttle_every=every, rows=rows,
        wall_platform=str(t.get("wall_platform", d.wall_platform)), lines=lines,
        **minutes,
    )


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
        commute=_commute(_table(raw, "commute")),
        api_key=_api_key(os.environ if environ is None else environ, path.parent / ".env"),
    )

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

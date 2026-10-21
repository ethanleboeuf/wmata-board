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

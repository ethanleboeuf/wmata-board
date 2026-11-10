"""What the man by home says to her: his morning send-off and his afternoon
cheer (wave.js draws them), a pair for each day of the week. config.toml's
[map.wave] has the defaults; these are the ones set since, kept in a tiny JSON
file so a restart keeps them.

Only something on the Pi itself may change them (kiosk-selector's page): see
from_tailnet.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_CHARS = 60
FIELDS = ("message", "cheer")
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# tailscale serve's proxy adds these to every request it forwards; a request
# from the Pi itself (kiosk-selector) has none of them.
_PROXY_HEADERS = ("tailscale-user-login", "x-forwarded-for", "x-forwarded-host")


@dataclass(frozen=True, slots=True)
class Words:
    """One day's pair."""
    message: str
    cheer: str

    def as_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Messages:
    days: tuple[Words, ...]   # one per DAYS, Monday first

    @classmethod
    def every_day(cls, words: Words) -> Messages:
        return cls((words,) * len(DAYS))

    def on(self, weekday: int) -> Words:
        """`weekday`: date.weekday(), Monday 0."""
        return self.days[weekday]

    def as_json(self) -> dict:
        return {d: w.as_json() for d, w in zip(DAYS, self.days)}


def from_tailnet(headers) -> bool:
    """True when the request came in through tailscale serve (the phone link)."""
    return any(h in headers for h in _PROXY_HEADERS)


def _parse_words(day: str, body: object, current: Words, defaults: Words) -> Words:
    if not isinstance(body, dict) or not any(k in body for k in FIELDS):
        raise ValueError(f"{day}: expected an object with message and/or cheer")
    out = current.as_json()
    for k in FIELDS:
        if k not in body:
            continue
        v = body[k]
        if not isinstance(v, str):
            raise ValueError(f"{day} {k}: a string")
        v = " ".join(v.split())
        if len(v) > MAX_CHARS:
            raise ValueError(f"{day} {k}: at most {MAX_CHARS} characters")
        out[k] = v or getattr(defaults, k)
    return Words(**out)


def parse_messages(body: object, current: Messages, defaults: Words) -> Messages:
    """Updated messages from a JSON body of {day: {message, cheer}}, any days;
    a blank one goes back to its default. ValueError says what's wrong."""
    if not isinstance(body, dict) or not body or any(k not in DAYS for k in body):
        raise ValueError("expected an object of days (monday...sunday), each with message and/or cheer")
    return Messages(tuple(_parse_words(d, body[d], w, defaults) if d in body else w
                          for d, w in zip(DAYS, current.days)))


def _load_words(saved: object, defaults: Words) -> Words:
    if not isinstance(saved, dict):
        return defaults
    return Words(**{k: str(saved.get(k) or getattr(defaults, k)) for k in FIELDS})


def load_messages(path: Path, defaults: Words) -> Messages:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Messages.every_day(defaults)
    if not isinstance(saved, dict):
        return Messages.every_day(defaults)
    if any(k in saved for k in FIELDS):   # saved before there was a pair per day
        return Messages.every_day(_load_words(saved, defaults))
    return Messages(tuple(_load_words(saved.get(d), defaults) for d in DAYS))


def save_messages(path: Path, messages: Messages) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(messages.as_json()), encoding="utf-8")
    except OSError:
        pass   # they still show until a restart

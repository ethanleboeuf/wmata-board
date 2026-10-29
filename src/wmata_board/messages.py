"""What the man by home says to her: his morning send-off and his afternoon
cheer (wave.js draws them). config.toml's [map.wave] has the defaults; these
are the ones set since, kept in a tiny JSON file so a restart keeps them.

Only something on the Pi itself may change them (kiosk-selector's page): see
from_tailnet.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_CHARS = 60
FIELDS = ("message", "cheer")
# tailscale serve's proxy adds these to every request it forwards; a request
# from the Pi itself (kiosk-selector) has none of them.
_PROXY_HEADERS = ("tailscale-user-login", "x-forwarded-for", "x-forwarded-host")


@dataclass(frozen=True, slots=True)
class Messages:
    message: str
    cheer: str

    def as_json(self) -> dict:
        return asdict(self)


def from_tailnet(headers) -> bool:
    """True when the request came in through tailscale serve (the phone link)."""
    return any(h in headers for h in _PROXY_HEADERS)


def parse_messages(body: object, current: Messages, defaults: Messages) -> Messages:
    """Updated messages from a JSON body; a blank one goes back to its default.
    ValueError says what's wrong."""
    if not isinstance(body, dict) or not any(k in body for k in FIELDS):
        raise ValueError("expected an object with message and/or cheer")
    out = current.as_json()
    for k in FIELDS:
        if k not in body:
            continue
        v = body[k]
        if not isinstance(v, str):
            raise ValueError(f"{k}: a string")
        v = " ".join(v.split())
        if len(v) > MAX_CHARS:
            raise ValueError(f"{k}: at most {MAX_CHARS} characters")
        out[k] = v or getattr(defaults, k)
    return Messages(**out)


def load_messages(path: Path, defaults: Messages) -> Messages:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return Messages(**{k: str(saved.get(k) or getattr(defaults, k)) for k in FIELDS})
    except (OSError, ValueError, AttributeError):
        return defaults


def save_messages(path: Path, messages: Messages) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(messages.as_json()), encoding="utf-8")
    except OSError:
        pass   # they still show until a restart

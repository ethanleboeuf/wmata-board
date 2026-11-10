"""The little hello she sends from her phone: an emoji and a few words that
float up on every open map. Pure; app.py keeps the latest one in memory (it
only matters for a minute, so no file).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

HELLO_EMOJI = ("💗", "👋", "😘", "🥳", "😴", "☕", "🐀")
HELLO_SHOW_S = 60          # a hello is still showing this long after it was sent
MAX_TEXT = 40


@dataclass(frozen=True, slots=True)
class Hello:
    id: int                # unique per send: maps play each id once
    emoji: str
    text: str
    at: float              # epoch s on the server's clock

    def as_json(self) -> dict:
        return asdict(self)


def parse_hello(body: object, now: float, previous: Hello | None = None) -> Hello:
    """A hello from the phone's JSON; ValueError says what's wrong."""
    if not isinstance(body, dict):
        raise ValueError("expected an object")
    emoji, text = body.get("emoji"), body.get("text")
    if not isinstance(emoji, str) or emoji not in HELLO_EMOJI:
        raise ValueError(f"emoji: one of {' '.join(HELLO_EMOJI)}")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise ValueError("text: a string")
    text = " ".join(text.split())
    if len(text) > MAX_TEXT:
        raise ValueError(f"text: at most {MAX_TEXT} characters")
    id_ = int(now * 1000)
    if previous is not None and id_ <= previous.id:
        id_ = previous.id + 1   # two sends in one millisecond, or a clock that stepped back
    return Hello(id_, emoji, text, now)


def hello_showing(hello: Hello | None, now: float) -> bool:
    return hello is not None and now - hello.at < HELLO_SHOW_S


def hello_age_s(hello: Hello, now: float) -> float:
    """Seconds since it was sent; the maps get this, not an epoch time, so a
    phone with a wrong clock still behaves."""
    return max(0.0, now - hello.at)

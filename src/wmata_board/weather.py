"""Open-Meteo, for the walk: parse the forecast, say what to bring. Pure,
except WeatherClient, which owns the one network call.

The request goes out on its own httpx client -- never WmataClient, whose
default headers carry the WMATA key -- with nothing identifying: a generic
User-Agent and coordinates rounded to ~1 km.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from .state import FeedState
from .wmata import WmataError

BASE_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 8.0
USER_AGENT = "wmata-board"
EXPIRE_AFTER_S = 3600.0        # an old forecast would mislead: show nothing instead

LOOKAHEAD_HOURS = 3            # a commute's worth
RAIN_LIKELY_PCT = 50
COLD_F = 40                    # feels-like at or below: a coat
BITTER_F = 25                  # ... at or below: bundle up
HOT_F = 90
WINDY_MPH = 20
DAY_HOURS = range(6, 20)       # sun-ish hours, for the clear-sky icon

_PARAMS = {
    "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
    "hourly": "temperature_2m,apparent_temperature,precipitation_probability,weather_code",
    "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    "timezone": "America/New_York", "forecast_days": "2",
}


@dataclass(frozen=True, slots=True)
class Hour:
    time: datetime                 # local, naive: Open-Meteo answers in the requested timezone
    feels: float | None
    pop: float | None              # precipitation probability, %
    code: int | None


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    time: datetime
    temp: float
    feels: float
    precip: float                  # mm in the current interval
    code: int
    wind: float                    # mph
    hours: tuple[Hour, ...]


class WeatherClient:
    def __init__(self, lat: float, lon: float, *, timeout: float = TIMEOUT_S,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._params = {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}", **_PARAMS}
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport,
                                       headers={"User-Agent": USER_AGENT})

    async def forecast(self) -> Any:
        try:
            r = await self._http.get(BASE_URL, params=self._params)
        except httpx.HTTPError as exc:
            raise WmataError("network", f"weather: {type(exc).__name__}") from None
        if r.status_code != 200:
            raise WmataError("http", f"weather: HTTP {r.status_code}")
        try:
            return r.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WmataError("parse", "weather: response was not JSON") from None

    async def aclose(self) -> None:
        await self._http.aclose()


def _num(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WmataError("parse", f"weather: {what} is {value!r}")
    return float(value)


def _opt(value: Any) -> float | None:
    return None if isinstance(value, bool) or not isinstance(value, (int, float)) else float(value)


def parse_weather(payload: Any) -> WeatherSnapshot:
    try:
        cur, hourly = payload["current"], payload["hourly"]
        hours = tuple(
            Hour(datetime.fromisoformat(t), _opt(f), _opt(p), None if c is None else int(c))
            for t, f, p, c in zip(hourly["time"], hourly["apparent_temperature"],
                                  hourly["precipitation_probability"], hourly["weather_code"]))
        return WeatherSnapshot(
            datetime.fromisoformat(cur["time"]), _num(cur["temperature_2m"], "temperature_2m"),
            _num(cur["apparent_temperature"], "apparent_temperature"),
            _num(cur["precipitation"], "precipitation"), int(_num(cur["weather_code"], "weather_code")),
            _num(cur["wind_speed_10m"], "wind_speed_10m"), hours)
    except WmataError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise WmataError("parse", f"weather: unexpected response ({type(exc).__name__})") from None


_SNOW = {71, 73, 75, 77, 85, 86}
_NAMES = {   # WMO code -> (icon, text); clear skies are handled by time of day
    2: ("⛅", "Partly cloudy"), 3: ("☁️", "Cloudy"), 45: ("🌫", "Fog"), 48: ("🌫", "Fog"),
    51: ("🌧", "Drizzle"), 53: ("🌧", "Drizzle"), 55: ("🌧", "Drizzle"),
    56: ("🌧", "Freezing drizzle"), 57: ("🌧", "Freezing drizzle"),
    61: ("🌧", "Rain"), 63: ("🌧", "Rain"), 65: ("🌧", "Heavy rain"),
    66: ("🌧", "Freezing rain"), 67: ("🌧", "Freezing rain"),
    71: ("❄️", "Snow"), 73: ("❄️", "Snow"), 75: ("❄️", "Heavy snow"), 77: ("❄️", "Snow"),
    80: ("🌧", "Showers"), 81: ("🌧", "Showers"), 82: ("🌧", "Heavy showers"),
    85: ("❄️", "Snow showers"), 86: ("❄️", "Snow showers"),
    95: ("⛈", "Thunderstorm"), 96: ("⛈", "Thunderstorm"), 99: ("⛈", "Thunderstorm"),
}


def _icon(code: int, hour: int) -> tuple[str, str]:
    if code in (0, 1):
        return ("☀️" if hour in DAY_HOURS else "🌙"), ("Clear" if code == 0 else "Mostly clear")
    return _NAMES.get(code, ("🌡", "Weather"))


def _clock(hour: int) -> str:
    return f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"


def _precip_hint(snap: WeatherSnapshot, window: list[Hour]) -> str | None:
    if snap.precip > 0:
        return "❄️ Snow now" if snap.code in _SNOW else "☔ Rain now"
    for h in window:
        if h.pop is not None and h.pop >= RAIN_LIKELY_PCT:
            return f"{'❄️ Snow' if h.code in _SNOW else '☔ Rain'} likely by {_clock(h.time.hour)}"
    return None


def _hints(snap: WeatherSnapshot, window: list[Hour]) -> list[str]:
    feels = round(snap.feels)
    out = [_precip_hint(snap, window)]
    if feels <= BITTER_F:
        out.append(f"🧣 Bundle up · feels like {feels}°")
    elif feels <= COLD_F:
        out.append(f"🧥 Feels like {feels}°")
    elif feels >= HOT_F:
        out.append(f"🥵 Feels like {feels}°")
    if snap.wind >= WINDY_MPH:
        out.append("💨 Windy")
    return [h for h in out if h][:2]


def weather_summary(snap: WeatherSnapshot | None, now_local: datetime) -> dict | None:
    if snap is None:
        return None
    start = now_local.replace(tzinfo=None, minute=0, second=0, microsecond=0)
    window = [h for h in snap.hours if start <= h.time < start + timedelta(hours=LOOKAHEAD_HOURS)]
    hints = _hints(snap, window)
    icon, text = _icon(snap.code, now_local.hour)
    return {"temp": round(snap.temp), "feels": round(snap.feels), "icon": icon, "text": text,
            "hint": hints[0] if hints else None, "hints": hints}


def weather_for(state: FeedState, now: float, now_local: datetime) -> dict | None:
    """The board's `weather`: nothing until a forecast arrives, nothing again
    once it is an hour old."""
    age = state.age(now)
    if state.value is None or age is None or age > EXPIRE_AFTER_S:
        return None
    return weather_summary(state.value, now_local)

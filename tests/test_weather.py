import json
from datetime import datetime

import httpx
import pytest

from helpers import ET, state

from wmata_board.fixtures import FixtureWeather
from wmata_board.weather import WeatherClient, parse_weather, weather_for, weather_summary
from wmata_board.wmata import WmataError


def payload(fixtures):
    return json.loads((fixtures / "weather.json").read_text(encoding="utf-8"))


def make(*, now="2026-10-20T06:15", temp=41.4, feels=35.2, precip=0.0, code=3, wind=5.0,
         hours=()):
    """A response whose hourly arrays are the given (hour, feels, pop, code) rows."""
    hours = list(hours)
    return parse_weather({
        "current": {"time": now, "temperature_2m": temp, "apparent_temperature": feels,
                    "precipitation": precip, "weather_code": code, "wind_speed_10m": wind},
        "hourly": {"time": [f"2026-10-20T{h:02d}:00" for h, *_ in hours],
                   "apparent_temperature": [f for _, f, _, _ in hours],
                   "precipitation_probability": [p for _, _, p, _ in hours],
                   "weather_code": [c for *_, c in hours]},
    })


AT = datetime(2026, 10, 20, 6, 15, tzinfo=ET)
MILD = [(6, 50, 0, 3), (7, 50, 0, 3), (8, 50, 0, 3), (9, 50, 90, 61)]   # 9 is outside the 3 hours


def test_parse_real_response(fixtures):
    snap = parse_weather(payload(fixtures))
    assert snap.time == datetime(2026, 11, 9, 23, 15)
    assert (snap.temp, snap.feels, snap.code) == (48.0, 43.4, 0)
    assert len(snap.hours) == 48 and snap.hours[0].time == datetime(2026, 11, 9, 0, 0)


@pytest.mark.parametrize("bad", [[], {}, {"current": {}}, {"current": {"time": "x"}, "hourly": {}}])
def test_bad_payload(bad):
    with pytest.raises(WmataError) as err:
        parse_weather(bad)
    assert err.value.kind == "parse"


def test_missing_current_field_is_a_parse_error(fixtures):
    p = payload(fixtures)
    del p["current"]["weather_code"]
    with pytest.raises(WmataError):
        parse_weather(p)


def test_null_hour_values_are_kept_but_never_counted(fixtures):
    p = payload(fixtures)
    p["hourly"]["precipitation_probability"][3] = None
    assert parse_weather(p).hours[3].pop is None
    snap = make(feels=60, hours=[(6, 50, None, 3), (7, 50, 0, 3)])
    assert weather_summary(snap, AT)["hints"] == []


def test_summary_shape_and_hints():
    snap = make(hours=[(6, 35, 10, 3), (7, 35, 20, 3), (8, 35, 60, 61), (9, 35, 90, 61)])
    s = weather_summary(snap, AT)
    assert s == {"temp": 41, "feels": 35, "icon": "☁️", "text": "Cloudy",
                 "hint": "☔ Rain likely by 8 AM", "hints": ["☔ Rain likely by 8 AM", "🧥 Feels like 35°"]}


def test_no_hints():
    s = weather_summary(make(feels=60, hours=MILD), AT)
    assert s["hint"] is None and s["hints"] == []


def test_rain_threshold_and_window():
    low = make(feels=60, hours=[(6, 50, 49, 61), (7, 50, 49, 61), (8, 50, 49, 61)])
    assert weather_summary(low, AT)["hints"] == []
    edge = make(feels=60, hours=[(6, 50, 0, 3), (7, 50, 0, 3), (8, 50, 50, 61)])
    assert weather_summary(edge, AT)["hint"] == "☔ Rain likely by 8 AM"
    assert weather_summary(make(feels=60, hours=MILD), AT)["hint"] is None   # the 90 % hour is the fourth


def test_past_hours_are_ignored():
    snap = make(feels=60, hours=[(4, 50, 90, 61), (5, 50, 90, 61), (6, 50, 0, 3), (7, 50, 0, 3)])
    assert weather_summary(snap, AT)["hint"] is None


def test_rain_hour_uses_the_twelve_hour_clock():
    noon = AT.replace(hour=11, minute=30)
    snap = make(now="2026-10-20T11:30", feels=60, hours=[(11, 50, 0, 3), (12, 50, 70, 61), (13, 50, 0, 3)])
    assert weather_summary(snap, noon)["hint"] == "☔ Rain likely by 12 PM"
    early = AT.replace(hour=0, minute=10)
    snap = make(now="2026-10-20T00:10", feels=60, hours=[(0, 50, 0, 3), (1, 50, 80, 61)])
    assert weather_summary(snap, early)["hint"] == "☔ Rain likely by 1 AM"


def test_snow_says_snow():
    snap = make(feels=60, hours=[(6, 50, 0, 3), (7, 50, 80, 73)])
    assert weather_summary(snap, AT)["hint"] == "❄️ Snow likely by 7 AM"


def test_already_precipitating_says_now():
    assert weather_summary(make(feels=60, precip=0.4, code=61, hours=MILD), AT)["hint"] == "☔ Rain now"
    assert weather_summary(make(feels=60, precip=0.4, code=71, hours=MILD), AT)["hint"] == "❄️ Snow now"


@pytest.mark.parametrize("feels, hint", [
    (41, None), (40, "🧥 Feels like 40°"), (26, "🧥 Feels like 26°"),
    (25, "🧣 Bundle up · feels like 25°"), (20, "🧣 Bundle up · feels like 20°"),
    (89, None), (90, "🥵 Feels like 90°"), (95, "🥵 Feels like 95°"),
])
def test_feels_like_hints(feels, hint):
    assert weather_summary(make(feels=feels, hours=MILD), AT)["hint"] == hint


def test_wind_hint_and_order_and_cap():
    assert weather_summary(make(feels=60, wind=20, hours=MILD), AT)["hints"] == ["💨 Windy"]
    assert weather_summary(make(feels=60, wind=19.9, hours=MILD), AT)["hints"] == []
    snap = make(feels=30, wind=25, hours=[(6, 30, 80, 61)])
    assert weather_summary(snap, AT)["hints"] == ["☔ Rain likely by 6 AM", "🧥 Feels like 30°"]   # at most two


def test_rounding():
    s = weather_summary(make(temp=40.6, feels=-3.6, hours=MILD), AT)
    assert (s["temp"], s["feels"]) == (41, -4)   # whole degrees


@pytest.mark.parametrize("code, icon, text", [
    (1, "☀️", "Mostly clear"), (2, "⛅", "Partly cloudy"), (45, "🌫", "Fog"), (53, "🌧", "Drizzle"),
    (63, "🌧", "Rain"), (81, "🌧", "Showers"), (73, "❄️", "Snow"), (95, "⛈", "Thunderstorm"),
])
def test_icons_by_code(code, icon, text):
    s = weather_summary(make(code=code, hours=MILD), AT)
    assert (s["icon"], s["text"]) == (icon, text)


def test_clear_is_a_moon_at_night():
    snap = make(code=0, hours=MILD)
    assert weather_summary(snap, AT.replace(hour=12))["icon"] == "☀️"
    assert weather_summary(snap, AT.replace(hour=5))["icon"] == "🌙"
    assert weather_summary(snap, AT.replace(hour=21))["icon"] == "🌙"


def test_unknown_code_still_summarises():
    s = weather_summary(make(code=1234, hours=MILD), AT)
    assert s["temp"] == 41 and s["text"] == "Weather"


def test_weather_for_age_and_missing():
    snap = make(hours=MILD)
    assert weather_for(state(None), 100.0, AT) is None
    assert weather_for(state(snap, fetched_at=100.0), 100.0 + 3600, AT)["temp"] == 41
    assert weather_for(state(snap, fetched_at=100.0), 100.0 + 3601, AT) is None
    assert weather_for(state(snap, fetched_at=None), 100.0, AT) is None


# ---- the client: its own httpx client, nothing identifying ----

def client_for(handler):
    return WeatherClient(38.8912, -77.0862, transport=httpx.MockTransport(handler))


async def test_request_is_plain_and_rounded(fixtures):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=payload(fixtures))

    c = client_for(handler)
    assert (await c.forecast())["current"]["weather_code"] == 0
    await c.aclose()
    (req,) = seen
    assert req.url.host == "api.open-meteo.com" and req.url.path == "/v1/forecast"
    assert req.url.params["latitude"] == "38.89" and req.url.params["longitude"] == "-77.09"
    assert req.url.params["temperature_unit"] == "fahrenheit" and req.url.params["forecast_days"] == "2"
    assert req.headers["user-agent"] == "wmata-board"
    assert not {"api_key", "authorization", "cookie"} & set(req.headers)


def test_client_has_the_eight_second_timeout_and_no_key_header():
    c = WeatherClient(38.89, -77.09)
    assert c._http.timeout.read == 8.0
    assert "api_key" not in c._http.headers


def _raise(exc):
    def handler(request):
        raise exc
    return handler


@pytest.mark.parametrize("handler, kind", [
    (lambda r: httpx.Response(500), "http"),
    (lambda r: httpx.Response(200, text="<html>"), "parse"),
    (_raise(httpx.ConnectError("down")), "network"),
    (_raise(httpx.ReadTimeout("slow")), "network"),
])
async def test_failures_are_wmata_errors(handler, kind):
    c = client_for(handler)
    with pytest.raises(WmataError) as err:
        await c.forecast()
    assert err.value.kind == kind
    await c.aclose()


async def test_fixture_weather_is_shifted_to_now(fixtures):
    now = datetime(2026, 3, 3, 8, 40, tzinfo=ET)
    snap = parse_weather(await FixtureWeather(fixtures / "weather.json", ET, clock=lambda: now).forecast())
    assert snap.time == datetime(2026, 3, 3, 8, 40)
    times = [h.time for h in snap.hours]
    assert datetime(2026, 3, 3, 8, 0) in times and datetime(2026, 3, 3, 11, 0) in times
    assert all(t.minute == 0 for t in times)

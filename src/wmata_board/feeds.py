"""Wire the client to Feed objects. The only module that knows which
endpoints feed which parts of the board."""

from __future__ import annotations

import time
from collections.abc import Callable

from .config import Config
from .incidents import parse_incidents
from .poller import Feed
from .positions import decode_positions
from .predictions import parse_predictions
from .service import station_data
from .trips import decode_trip_updates
from .weather import parse_weather

STATION_CADENCE_S = 86400.0   # names, lines and first/last trains change rarely


def build_feeds(config: Config, client, *, network_loader=None, schedule_loader=None, weather=None,
                clock: Callable[[], float] = time.monotonic) -> dict[str, Feed]:
    """`weather`: anything with an async `forecast()` (WeatherClient, or the
    fixtures stand-in); no [weather] in the config or none given, no feed."""
    code = config.board.station
    idle = config.polling.idle_after

    async def arrivals():   # every station in one call: the phone can pick any
        return parse_predictions(await client.predictions(["All"]), None)

    async def incidents():
        return parse_incidents(await client.incidents())

    async def station():
        return station_data(code, await client.station_info(code), await client.station_times(code))

    async def positions():
        return decode_positions(await client.vehicle_positions())

    feeds = {
        "arrivals": Feed("arrivals", arrivals, config.polling.arrivals, idle_after=idle, clock=clock),
        "incidents": Feed("incidents", incidents, config.polling.incidents, idle_after=idle, clock=clock),
        "positions": Feed("positions", positions, config.polling.positions, idle_after=idle, clock=clock),
        "station": Feed("station", station, STATION_CADENCE_S, gated=False, clock=clock),
    }
    if network_loader is not None:   # hourly check; the cache decides when to download
        feeds["network"] = Feed("network", network_loader.load, 3600.0, gated=False, clock=clock)
    if config.commute is not None:
        async def trips():
            return decode_trip_updates(await client.trip_updates())   # all stations: trip cards

        feeds["trips"] = Feed("trips", trips, config.polling.trips, idle_after=idle, clock=clock)
        if schedule_loader is not None:
            feeds["schedule"] = Feed("schedule", schedule_loader.load, 3600.0, gated=False, clock=clock)
    if config.weather is not None and weather is not None:   # not a WMATA call: its own client
        async def forecast():
            return parse_weather(await weather.forecast())

        feeds["weather"] = Feed("weather", forecast, config.polling.weather, idle_after=idle, clock=clock)
    return feeds

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

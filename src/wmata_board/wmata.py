"""The one place that talks to api.wmata.com.

Every failure comes out as a WmataError with a short `kind` the board can act
on (an expired key reads differently from a network blip). Messages name the
endpoint, never the key.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import httpx

BASE_URL = "https://api.wmata.com"
TIMEOUT_S = 8.0
STATIC_TIMEOUT_S = 60.0  # the GTFS static zip is ~3 MB


class WmataError(Exception):
    """kind: no_key | api_key | rate_limited | http | network | parse"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class WmataClient:
    def __init__(self, api_key: str | None, *, base_url: str = BASE_URL,
                 timeout: float = TIMEOUT_S,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._has_key = bool(api_key)
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport,
            headers={"api_key": api_key} if api_key else {},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict | None = None,
                   timeout: float | None = None) -> httpx.Response:
        if not self._has_key:
            raise WmataError("no_key", "No WMATA API key configured")
        try:
            if timeout is None:
                resp = await self._http.get(path, params=params)
            else:
                resp = await self._http.get(path, params=params, timeout=timeout)
        except httpx.TimeoutException:
            raise WmataError("network", f"timed out fetching {path}") from None
        except httpx.HTTPError as exc:
            raise WmataError("network", f"{type(exc).__name__} fetching {path}") from None
        if resp.status_code in (401, 403):
            raise WmataError("api_key", f"WMATA rejected the API key (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise WmataError("rate_limited", "WMATA rate limit hit (HTTP 429)")
        if resp.status_code >= 400:
            raise WmataError("http", f"HTTP {resp.status_code} from {path}")
        return resp

    async def _json(self, path: str, params: dict | None = None) -> Any:
        resp = await self._get(path, params)
        try:
            return resp.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise WmataError("parse", f"bad JSON from {path}") from None

    async def predictions(self, stations: Sequence[str]) -> Any:
        return await self._json(f"/StationPrediction.svc/json/GetPrediction/{','.join(stations)}")

    async def incidents(self) -> Any:
        return await self._json("/Incidents.svc/json/Incidents")

    async def station_info(self, code: str) -> Any:
        return await self._json("/Rail.svc/json/jStationInfo", {"StationCode": code})

    async def station_times(self, code: str) -> Any:
        return await self._json("/Rail.svc/json/jStationTimes", {"StationCode": code})

    async def vehicle_positions(self) -> bytes:
        return (await self._get("/gtfs/rail-gtfsrt-vehiclepositions.pb")).content

    async def trip_updates(self) -> bytes:
        return (await self._get("/gtfs/rail-gtfsrt-tripupdates.pb")).content

    async def gtfs_static(self) -> bytes:
        return (await self._get("/gtfs/rail-gtfs-static.zip", timeout=STATIC_TIMEOUT_S)).content

import json

import httpx
import pytest

from wmata_board.fixtures import FixtureClient
from wmata_board.wmata import WmataClient, WmataError

KEY = "test-key-123"


def client_for(handler) -> WmataClient:
    return WmataClient(KEY, base_url="https://api.test", transport=httpx.MockTransport(handler))


async def test_sends_header_and_builds_prediction_path():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("api_key")
        return httpx.Response(200, json={"Trains": []})

    assert await client_for(handler).predictions(["K01", "C05"]) == {"Trains": []}
    assert seen["url"] == "https://api.test/StationPrediction.svc/json/GetPrediction/K01,C05"
    assert seen["key"] == KEY


async def test_station_endpoints_use_station_code_param():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={})

    c = client_for(handler)
    await c.station_info("K01")
    await c.station_times("K01")
    await c.incidents()
    assert urls == [
        "https://api.test/Rail.svc/json/jStationInfo?StationCode=K01",
        "https://api.test/Rail.svc/json/jStationTimes?StationCode=K01",
        "https://api.test/Incidents.svc/json/Incidents",
    ]


async def test_binary_endpoints_return_bytes():
    def handler(request):
        return httpx.Response(200, content=b"\x0a\x00")

    c = client_for(handler)
    assert await c.vehicle_positions() == b"\x0a\x00"
    assert await c.gtfs_static() == b"\x0a\x00"


@pytest.mark.parametrize("status, kind", [(401, "api_key"), (403, "api_key"), (429, "rate_limited"),
                                          (400, "http"), (500, "http"), (503, "http")])
async def test_status_codes_map_to_kinds(status, kind):
    c = client_for(lambda r: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(WmataError) as err:
        await c.incidents()
    assert err.value.kind == kind
    assert KEY not in err.value.message


async def test_network_failure_is_network_kind():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(WmataError) as err:
        await client_for(handler).incidents()
    assert err.value.kind == "network"


async def test_timeout_is_network_kind():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(WmataError) as err:
        await client_for(handler).incidents()
    assert err.value.kind == "network"


async def test_bad_json_is_parse_kind():
    c = client_for(lambda r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(WmataError) as err:
        await c.incidents()
    assert err.value.kind == "parse"


async def test_no_key_never_calls_out():
    def handler(request):
        raise AssertionError("must not be called")

    c = WmataClient(None, transport=httpx.MockTransport(handler))
    with pytest.raises(WmataError) as err:
        await c.predictions(["K01"])
    assert err.value.kind == "no_key"


async def test_fixture_client_reads_files(fixtures):
    c = FixtureClient(fixtures)
    data = await c.predictions(["K01"])
    assert data == json.loads((fixtures / "predictions_K01.json").read_text(encoding="utf-8"))
    assert (await c.station_info("K01"))["Name"] == "Court House"
    assert "StationTimes" in await c.station_times("K01")


async def test_fixture_client_cycles_positions(fixtures):
    c = FixtureClient(fixtures)
    files = sorted((fixtures / "positions").glob("*.pb"))
    got = [await c.vehicle_positions() for _ in range(len(files) + 1)]
    assert got[0] == files[0].read_bytes()
    assert got[1] == files[1].read_bytes()
    assert got[-1] == files[0].read_bytes()


async def test_fixture_client_missing_file_is_wmata_error(tmp_path):
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).incidents()
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).vehicle_positions()
    with pytest.raises(WmataError):
        await FixtureClient(tmp_path).gtfs_static()

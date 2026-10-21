import pytest
from google.transit import gtfs_realtime_pb2

from wmata_board.positions import cars_from_plate, decode_positions
from wmata_board.wmata import WmataError


@pytest.mark.parametrize("plate, cars", [
    ("8_7202-7203.7111-7110.7341-7340.7299-7298", 8), ("6_1", 6), ("", None), ("x_1", None), ("8", 8),
])
def test_cars_from_plate(plate, cars):
    assert cars_from_plate(plate) == cars


def feed(*entities, ts=1792551838):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = ts
    for i, (route, lat, lon, bearing, plate, has_pos) in enumerate(entities):
        e = msg.entity.add()
        e.id = f"e{i}"
        v = e.vehicle
        if route is not None:
            v.trip.route_id = route
            if i == 0:
                v.trip.trip_id = "t-or-1"
        if has_pos:
            v.position.latitude, v.position.longitude = lat, lon
            if bearing is not None:
                v.position.bearing = bearing
        v.vehicle.id = f"v{i}"
        v.vehicle.license_plate = plate
    return msg.SerializeToString()


def test_synthetic_feed_filters_and_maps():
    data = feed(("ORANGE", 38.89, -77.08, 90.0, "8_1-2", True),
                ("SILVER", 38.90, -77.07, None, "", True),
                ("BUS", 38.9, -77.0, 0.0, "6_1", True),        # unknown route
                (None, 38.9, -77.0, 0.0, "6_1", True),         # no trip
                ("RED", 0, 0, 0.0, "6_1", False))              # no position
    snap = decode_positions(data)
    assert snap.feed_timestamp == 1792551838
    assert [(v.id, v.line, v.cars, v.heading) for v in snap.vehicles] == \
        [("v0", "OR", 8, 90.0), ("v1", "SV", None, None)]
    assert snap.vehicles[0].lat == pytest.approx(38.89, abs=1e-5)
    assert snap.vehicles[0].as_json() == {"id": "v0", "line": "OR", "lat": snap.vehicles[0].lat,
                                          "lon": snap.vehicles[0].lon, "heading": 90.0, "cars": 8,
                                          "trip_id": "t-or-1"}
    assert snap.vehicles[1].trip_id is None


def test_recorded_snapshot(fixtures):
    path = sorted((fixtures / "positions").glob("*.pb"))[0]
    snap = decode_positions(path.read_bytes())
    assert snap.feed_timestamp > 1_700_000_000
    assert len(snap.vehicles) > 20
    assert {v.line for v in snap.vehicles} <= {"RD", "OR", "SV", "BL", "GR", "YL"}
    assert {v.cars for v in snap.vehicles} <= {6, 8, None}
    assert all(38.5 < v.lat < 39.3 and -77.6 < v.lon < -76.7 for v in snap.vehicles)


def test_garbage_is_parse_error():
    with pytest.raises(WmataError) as err:
        decode_positions(b"\xff\xff\xff\xff")
    assert err.value.kind == "parse"


def test_fixture_client_stamps_snapshots_now(fixtures):
    import asyncio, time
    from wmata_board.fixtures import FixtureClient
    snap = decode_positions(asyncio.run(FixtureClient(fixtures).vehicle_positions()))
    assert abs(snap.feed_timestamp - time.time()) < 5
    assert len(snap.vehicles) > 20

import json

import pytest
from fastapi.testclient import TestClient

from helpers import config

from conftest import REPO
from wmata_board.app import create_app
from wmata_board.fixtures import FixtureClient


@pytest.fixture
def client(tmp_path, fixtures):
    (tmp_path / "basemap.pmtiles").write_bytes(bytes(range(256)) * 4)   # 1024 bytes
    app = create_app(config(), FixtureClient(fixtures), start_polling=False, data_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_full_file(client):
    r = client.get("/basemap.pmtiles")
    assert r.status_code == 200 and len(r.content) == 1024
    assert r.headers["accept-ranges"] == "bytes"


@pytest.mark.parametrize("header, start, end", [("bytes=0-15", 0, 15), ("bytes=1000-", 1000, 1023),
                                                ("bytes=-24", 1000, 1023), ("bytes=10-5000", 10, 1023)])
def test_ranges(client, header, start, end):
    r = client.get("/basemap.pmtiles", headers={"Range": header})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes {start}-{end}/1024"
    assert r.content == (bytes(range(256)) * 4)[start:end + 1]


@pytest.mark.parametrize("header", ["bytes=2000-", "bytes=9-3", "items=0-1", "bytes=-"])
def test_bad_ranges(client, header):
    r = client.get("/basemap.pmtiles", headers={"Range": header})
    assert r.status_code == 416
    assert r.headers["content-range"] == "bytes */1024"


def test_head(client):
    r = client.head("/basemap.pmtiles")
    assert r.status_code == 200 and r.headers["content-length"] == "1024"


def test_missing_basemap_is_404(tmp_path, fixtures):
    """Review focus 5: no basemap yet -> clean 404 the page can handle."""
    app = create_app(config(), FixtureClient(fixtures), start_polling=False, data_dir=tmp_path / "empty")
    with TestClient(app) as c:
        assert c.get("/basemap.pmtiles").status_code == 404
        assert c.head("/basemap.pmtiles").status_code == 404


def test_style_is_board_navy():
    style = json.loads((REPO / "web" / "style.json").read_text(encoding="utf-8"))
    assert style["version"] == 8
    assert "glyphs" not in style and "sprite" not in style        # no symbol layers
    assert all(layer["type"] != "symbol" for layer in style["layers"])
    colors = json.dumps(style)
    for c in ("#0f151d", "#0c2742", "#151e29", "#24324a", "#33465f"):
        assert c in colors
    assert "OpenStreetMap" in style["sources"]["protomaps"]["attribution"]


def test_vendor_files_present():
    for name in ("maplibre-gl.js", "maplibre-gl.css", "pmtiles.js"):
        assert (REPO / "web" / "vendor" / name).stat().st_size > 10_000

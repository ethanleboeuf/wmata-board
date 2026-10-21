import re

from conftest import REPO

WEB = REPO / "web"


def test_no_remote_urls_in_pages():
    for path in list(WEB.glob("*.html")) + list(WEB.glob("*.css")) + list(WEB.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", text), f"remote URL in {path.name}"


def test_fonts_vendored():
    for weight in (500, 600, 700, 800):
        data = (WEB / "fonts" / f"inter-latin-{weight}-normal.woff2").read_bytes()
        assert data[:4] == b"wOF2" and len(data) > 10_000


def test_static_references_exist():
    for page in WEB.glob("*.html"):
        for ref in re.findall(r'(?:src|href)="/static/([^"]+)"', page.read_text(encoding="utf-8")):
            assert (WEB / ref).exists(), f"{page.name} references missing {ref}"

"""Entry point: `python -m wmata_board [--config config.toml] [--fixtures DIR]`."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from . import __version__
from .app import PROJECT_ROOT, create_app
from .config import ConfigError, load_config
from .fixtures import FixtureClient
from .wmata import WmataClient

DEFAULT_CONFIG = PROJECT_ROOT / "config.toml"
log = logging.getLogger("wmata_board")


def build_version() -> str:
    """Changes on every deploy, so open pages know to reload themselves."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    return f"{__version__}+{sha or int(time.time())}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wmata_board", description="Court House departure board.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fixtures", type=Path, default=None,
                        help="replay recorded responses from this directory instead of calling WMATA")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-level", default="info",
                        choices=["critical", "error", "warning", "info", "debug"])
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.fixtures:
        client = FixtureClient(args.fixtures)
        log.info("fixtures mode: replaying %s", args.fixtures)
        if config.api_key is None:   # fixtures need no key, but the board would say "no key"
            from dataclasses import replace
            config = replace(config, api_key="fixtures")
    else:
        client = WmataClient(config.api_key)
        if config.api_key is None:
            log.warning("no WMATA_API_KEY set: the board will say so until one is configured")

    host = args.host or config.server.host
    port = args.port or config.server.port
    log.info("wmata-board on http://%s:%d/ (station %s)", host, port, config.board.station)
    uvicorn.run(create_app(config, client, version=build_version()),
                host=host, port=port, log_level=args.log_level, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

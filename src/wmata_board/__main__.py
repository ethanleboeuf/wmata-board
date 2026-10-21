"""Entry point: `python -m wmata_board [--config config.toml] [--fixtures DIR]`."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

from . import __version__
from .app import DATA_DIR, PROJECT_ROOT, create_app
from .config import ConfigError, load_config
from .fixtures import FixtureClient
from .network import FixtureNetwork, NetworkCache
from .trips import FixtureSchedule, build_schedule
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
        network_loader = FixtureNetwork(args.fixtures / "network.json")
        schedule_loader = FixtureSchedule(args.fixtures / "schedule.json", ZoneInfo(config.board.timezone))
        log.info("fixtures mode: replaying %s", args.fixtures)
        if config.api_key is None:   # fixtures need no key, but the board would say "no key"
            from dataclasses import replace
            config = replace(config, api_key="fixtures")
    else:
        client = WmataClient(config.api_key)
        network_loader = NetworkCache(client, DATA_DIR / "network.json")
        schedule_loader = None
        if config.commute is not None:
            stations = config.commute.stations
            schedule_loader = NetworkCache(client, DATA_DIR / "schedule.json", key=",".join(stations),
                                           build=partial(build_schedule, stations=stations))
        if config.api_key is None:
            log.warning("no WMATA_API_KEY set: the board will say so until one is configured")

    host = args.host or config.server.host
    port = args.port or config.server.port
    log.info("wmata-board on http://%s:%d/ (station %s)", host, port, config.board.station)
    uvicorn.run(create_app(config, client, version=build_version(), network_loader=network_loader,
                           schedule_loader=schedule_loader),
                host=host, port=port, log_level=args.log_level, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

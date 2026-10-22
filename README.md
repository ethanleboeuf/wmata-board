# wmata-board

A departure board for Court House (K01): a FastAPI service that polls the WMATA
APIs, plus a vanilla-JS wall page (and a phone page with a live map, added in
later milestones). It runs on the Raspberry Pi as a systemd user unit on
`127.0.0.1:8766`.

- Wall: kiosk-selector target `metro` (https://raspberrypi.tail7b0b4d.ts.net:8445)
- Phone: https://raspberrypi.tail7b0b4d.ts.net:8446/phone. Tap the station name
  to see arrivals at any station (search, or 📍 Nearest); it starts on Court
  House each time it opens. The wall always shows Court House.

## Local development

```
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # .venv/bin/pip on Linux/macOS
.venv/Scripts/python -m wmata_board --fixtures tests/fixtures
.venv/Scripts/python -m pytest -q
node --test tests/js/*.test.js             # glob form; the directory form fails on Node 24
```

## Configuration

`config.toml` (commented) holds stations, lines, polling intervals and map
settings. The API key is not in it: set `WMATA_API_KEY` in `~/wmata-board.env`
on the Pi (`chmod 600`) or a gitignored `.env` locally.

## Commute panel

Weekday mornings (6:30–8:10) the wall and phone show a Children's National
panel: every Court House train with its Metro Center wait, Brookland arrival
and the Brookland shuttle it makes. Weekday evenings (4:00–6:30) the phone
shows the way home from the hospital or Takoma. On the phone, the morning panel
can also end at Takoma instead of the shuttle, and the **Commute** button (top
right) opens the panel at any time, with a Morning/Evening switch, or hides it.
Settings live in `[commute]` in
`config.toml`. Preview it at any time of day with `?commute=am&at=7:30` (or
`commute=pm&at=17:00`) on `/` or `/phone`. The timetable is cached in
`data/schedule.json` and rebuilt daily. Rows marked `sched` come from the
timetable because live predictions don't reach that far ahead yet.

## Pi setup

```
cd ~ && git clone git@github.com:ethanleboeuf/wmata-board.git
cd wmata-board && python3 -m venv .venv && .venv/bin/pip install -e .
echo 'WMATA_API_KEY=...' > ~/wmata-board.env && chmod 600 ~/wmata-board.env
mkdir -p ~/.config/systemd/user && cp deploy/wmata-board.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now wmata-board
loginctl enable-linger $USER     # lets the user unit start at boot without a login
```

- Basemap: run `tools/build_basemap.sh` (added with the live map, milestone 5). After
  rebuilding it, reload the kiosk page / phone: browsers may cache old byte ranges for a day.
- Phone page: expose it with `tailscale serve` on :8446 to `http://127.0.0.1:8766`
  (e.g. `tailscale serve --bg --https=8446 http://127.0.0.1:8766`).
- Wall: add a `metro` target (`http://localhost:8766/`) to `~/kiosk-selector/targets.py`
  and restart kiosk-selector.

## Deploy an update

```
git push
ssh raspberrypi 'cd ~/wmata-board && git pull --ff-only && .venv/bin/pip install -e . -q && systemctl --user restart wmata-board'
```

Open pages reload themselves when they see the new version.

## Troubleshooting

- Logs: `journalctl _SYSTEMD_USER_UNIT=wmata-board.service -f`
  (`journalctl --user -u wmata-board` says "No journal files" on this Pi: the user journal
  isn't persisted, so entries land in the system journal, readable via the `adm` group.)
- Health: `curl -s localhost:8766/healthz`
- Status pill: amber = WMATA data is old; red = the page can't reach the service.
- "WMATA rejected the API key": check `~/wmata-board.env`.
- WMATA quirks (`NewCrlton`, `LastTrain` destinations) are mapped in
  `DESTINATION_ALIASES` in `src/wmata_board/predictions.py`.
- Refresh test fixtures from live data: `tools/record_fixtures.py` (see its docstring;
  `--commute YYYY-MM-DD` records `trip_updates.pb` and that weekday's `schedule.json`).

## Data & licenses

Train data is from WMATA and subject to the WMATA developer terms. Basemap data
(c) OpenStreetMap contributors via Protomaps (ODbL). Inter font: SIL OFL.
MapLibre GL: BSD-3-Clause.

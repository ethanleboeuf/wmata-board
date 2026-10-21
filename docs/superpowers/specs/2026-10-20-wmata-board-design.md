# WMATA board — design

Date: 2026-10-20 · Status: draft for review

## Goal

A glanceable, always-on departure board for Court House (K01) on the Raspberry
Pi's wall display, readable from across the room: live arrivals by platform,
service alerts for the station's lines, and a live map of trains moving through
Arlington and downtown DC. The same service also gives a phone view over
Tailscale for checking where trains are.

Success: the board runs for weeks unattended, shows correct arrivals within
WMATA's own ~20–30 s refresh, says clearly when its data is stale, never
crash-loops, and is one button in kiosk-selector.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Station | Court House (K01) only; config takes a list for later. K01 serves OR + SV only (verified via `jStationInfo`). |
| Kiosk | Not its own kiosk. A kiosk-selector target (`metro`), shown in the existing `kiosk.service` chromium. |
| Look | Modern Metro LCD: Inter, near-black `#0d1117`, round line chips, ARR/BRD in yellow `#ffd166`. |
| Layout (wall) | Header (station + clock). Alert banner full-width under header when active. Left 54 %: arrivals stacked by direction, 3 rows each. Right 46 %: live map. |
| Map area | "Arlington + downtown": lon −77.122…−76.978, lat 38.844…38.966 (Ballston → Brookland/Navy Yard). |
| Basemap | Self-hosted OpenStreetMap vector tiles (Protomaps extract, ODbL, attribution "© OpenStreetMap contributors"), drawn by MapLibre GL with our "Board navy" style. No keys, no runtime tile service. |
| Palette (Board navy) | land `#0f151d`, water `#0c2742`, minor features `#151e29`, streets `#24324a`, major streets `#33465f`, place labels `#3b4a5e`. |
| Map overlay | SVG on top of MapLibre: real track geometry from WMATA rail GTFS shapes, shared track drawn as parallel lanes, hollow-ring stations (larger at transfers), signage-caps labels, place names (Georgetown, The Mall, Arlington, Washington), Brookland labeled, **Children's National** coral `+` badge at 38.92711, −77.01417, Court House ring + pulse. |
| Trains | **Glow + line badge**: soft glow in line color, line-color bullet with letter (R/O/S/B/G/Y), white heading arrowhead. Positions glide along the track between updates. |
| Phone | `/phone` page over Tailscale HTTPS: full-screen pannable/zoomable map (starts on the wall's view, can zoom out to the whole system) plus a bottom sheet with K01 arrivals and alerts. |
| Stack | Python 3.13, FastAPI + uvicorn + httpx (matches skyview), vanilla JS, MapLibre GL vendored. |
| Repo | Private GitHub repo `wmata-board`; the Pi clones it to `~/wmata-board`. |

## WMATA data (verified 2026-10-20 against docs and live calls)

Auth: `api_key` request header. Missing key → 401 JSON `{statusCode, message}`;
bad station → 400 `{"Message": ...}`. Default tier reportedly 10 calls/s,
50,000/day (third-party source; portal shows tiers only when logged in).

| Feed | Endpoint | Cadence | Notes |
|---|---|---|---|
| Arrivals | `StationPrediction.svc/json/GetPrediction/{codes}` | 20 s | WMATA refreshes every 20–30 s. `Min`: number, `ARR`, `BRD`, `---`, `""`. `Group` = platform/track (K01: 1 = eastbound, 2 = westbound). `DestinationCode` can be null with an abbreviated `DestinationName` (seen: `"NewCrlton"`). `Line` may be blank/`No`. |
| Rail incidents | `Incidents.svc/json/Incidents` | 60 s | `LinesAffected` is `"OR; SV;"`-style, split on `;\s?`. |
| Train positions | `gtfs/rail-gtfsrt-vehiclepositions.pb` (GTFS-RT protobuf) | 5 s | lat/lon/bearing, `trip.route_id` (RED, ORANGE, …), `vehicle.id`, `vehicle.license_plate` = `"<cars>_<car numbers>"`. Feed changes every ~3–7 s. |
| Station info / times | `Rail.svc/json/jStationInfo`, `jStationTimes` | daily | Lines served, name ("Court House"), first/last trains. |
| Network geometry | `gtfs/rail-gtfs-static.zip` (~3 MB) | daily | `shapes.txt` (longest shape per route), `stops.txt` (`location_type=1` stations; transfer stations have combined IDs like `STN_A01_C01`). Cached in `data/`. |

Budget with everything polling continuously: ~14,400 calls/day (29 %). Demand
gating (below) means far fewer in practice.

## Architecture

One process (`python -m wmata_board --config config.toml`):

```
src/wmata_board/
  config.py       load + validate config.toml; API key from env / .env
  wmata.py        httpx client: header auth, 8 s timeout, maps failures to typed errors
  predictions.py  parse + normalize arrivals (pure)
  incidents.py    filter incidents to configured lines (pure)
  positions.py    decode GTFS-RT → vehicles (pure, gtfs-realtime-bindings)
  network.py      GTFS static → per-line shapes + stations; disk cache
  poller.py       one task per feed: cadence, demand gating, backoff
  state.py        last-known value + fetched_at + last error per feed
  app.py          routes + static files
web/
  index.html board.css board.js   wall board (fixed 1920×1080 stage, scaled to fit)
  phone.html phone.css phone.js   phone view
  map.js                          shared map: MapLibre basemap + SVG overlay + glide
  style.json                      Board-navy MapLibre style (no glyph/sprite needs)
  fonts/ vendor/                  Inter woff2, maplibre-gl, pmtiles: all local
tools/build_basemap.sh            one-time pmtiles extract → data/basemap.pmtiles
tools/record_fixtures.py          capture live responses into tests/fixtures/
deploy/wmata-board.service        systemd --user unit
```

### API (local JSON)

- `GET /api/board` → `{station, generated_at, version, platforms: [{group, label, trains: [{line, cars, destination, minutes, display}]}], alerts: [{id, lines, text, updated}], service: {first_train, last_train}, freshness: {arrivals: {age_s, stale, error}, incidents: {...}}}`
- `GET /api/positions` → `{fetched_at, age_s, stale, vehicles: [{id, line, lat, lon, heading, cars}]}`
- `GET /api/network` → `{lines: {RED: [[lon, lat], ...]}, stations: [{codes, name, lon, lat, transfer}], landmarks, view}` (changes daily; cached by the browser).
- `GET /basemap.pmtiles` → served with HTTP Range support (MapLibre's pmtiles protocol reads by range).
- `GET /healthz` → 200 with per-feed freshness (for quick checks over SSH).

### Polling and demand gating

Each feed has its own asyncio task. A feed is polled only while someone wants
it: the board/phone pages call `/api/board` every 5 s and `/api/positions`
every 5 s, and each request marks its feed "wanted" for 90 s. With nobody
viewing (the wall showing skyview, no phone open), WMATA isn't called at all.
The first request after idle triggers an immediate fetch, so switching to the
board shows fresh data within ~1 s.

Failures: per-feed exponential backoff (cadence → 2× … max 5 min), reset on
success. 401/403 → status `api_key` (shown on the board), 429 → backoff. No
exception escapes a task; the process never exits because WMATA is down.
Missing API key → service still starts, board shows "No WMATA API key
configured".

### Arrivals rules

- Keep trains whose `LocationCode` is a configured station and whose `Line` is a configured line; drop no-passenger trains (`Line` blank/`No`/`--`, or destination "No Passenger"/"ssenger").
- Destination: `DestinationName` if `DestinationCode` is set; else alias table (`NewCrlton` → New Carrollton, extensible); else raw `Destination`; empty → "Train".
- Order within a platform: `BRD`, `ARR`, then ascending minutes; `---`/blank last, displayed "—". Show the first N (`rows_per_direction`, default 3).
- Platform labels from config (`[stations.K01.platforms] 1 = "To Washington · New Carrollton"`); unconfigured groups default to "To " + distinct destinations.
- No trains and outside the station's service window → "No trains · service resumes 5:13 AM".

### Staleness (wall + phone)

- Header pill hidden when fresh; amber "Updated 2 min ago" when arrivals > 60 s old; red "Board offline" if the browser can't reach the backend.
- Arrivals older than 10 min are replaced by "Live arrivals unavailable" (old minutes would mislead).
- Trains on the map fade out when positions are > 2 min old.
- The page never needs a reload to recover; it reloads itself only when `/api/board` reports a new `version` (after a deploy).

### Alerts

Incidents whose lines intersect the station's configured lines. Banner under
the header: amber background, "ALERT" tag, line chips, text clamped to two
lines; several alerts rotate every 10 s. No alerts → no banner, panels reclaim
the space.

### Map

- MapLibre renders only the basemap (non-interactive on the wall, interactive on the phone); the overlay is SVG re-projected with `map.project()` on every render, so the same `map.js` serves both.
- Lanes: fixed per-line offsets in screen pixels (OR −0.5, SV +0.5, BL +1.5, GR −0.5, YL +0.5 line widths), as prototyped.
- Glide: the browser keeps the previous and latest snapshot per vehicle, snaps both to the vehicle's lane (arc length), and animates between them over the measured interval between snapshots. That puts the display ~5–10 s behind real time with smooth motion. Jumps > ~1 km or a line change snap instead of gliding; vehicles leaving the view fade.
- Only revenue trains with a known route are drawn.
- Basemap extract covers the whole Metrorail system (for the phone's zoom-out), maxzoom 15; `tools/build_basemap.sh` documents the exact `pmtiles extract` command and the bbox.

### Phone view

`https://raspberrypi.tail7b0b4d.ts.net:8446/phone` (new `tailscale serve`
mapping → `127.0.0.1:8766`). Full-screen map with pinch/pan, a "recenter"
button, and a draggable bottom sheet with K01 arrivals and alerts. Same data
endpoints as the wall. The wall board is also reachable at `/`.

## Configuration

`config.toml` (committed, no secrets):

```toml
[board]
stations = ["K01"]
lines = ["OR", "SV"]          # omit to use every line the station serves
rows_per_direction = 3
timezone = "America/New_York"

[stations.K01.platforms]
1 = "To Washington · New Carrollton"
2 = "To Vienna · Ashburn"

[polling]                      # seconds
arrivals = 20
incidents = 60
positions = 5
idle_after = 90

[map]
bbox = [-77.122, 38.844, -76.978, 38.966]   # west, south, east, north
labels = ["K04", "K02", "C05", "C04", "C01", "D03", "B03", "A03", "C07", "F05", "B05"]
places = [["GEORGETOWN", 38.9085, -77.0665], ["THE MALL", 38.8873, -77.0405], ["ARLINGTON", 38.8705, -77.106], ["WASHINGTON", 38.9335, -77.096]]

[[map.landmarks]]
name = "Children's National"
lat = 38.92711
lon = -77.01417
style = "hospital"

[server]
host = "127.0.0.1"
port = 8766
```

`WMATA_API_KEY` from the environment or `.env` (gitignored); `.env.example`
committed.

## Deployment

- GitHub private repo `wmata-board`; Pi: `git clone` to `~/wmata-board`, `python3 -m venv .venv`, `pip install -e .`.
- `deploy/wmata-board.service`: `systemd --user` unit (like skyview's): `Type=exec`, `Restart=always`, `RestartSec=5`, `TimeoutStopSec=10`, journal output, `EnvironmentFile=%h/wmata-board/.env`.
- kiosk-selector: add `"metro": "http://localhost:8766/"` to `~/kiosk-selector/targets.py`, commit there, restart it.
- Tailscale: `tailscale serve --bg --https=8446 http://127.0.0.1:8766`.
- Basemap: run `tools/build_basemap.sh` once on the Pi (downloads the extract into `data/`).
- README: setup, config, update/deploy steps, troubleshooting.

## Testing

- pytest with recorded fixtures (no live key needed): K01 predictions (including the `NewCrlton` case), synthetic ARR/BRD/`---`/blank/no-passenger/missing-destination cases, incidents (empty, matching, non-matching, `LinesAffected` variants), a GTFS-RT `.pb` snapshot, station info/times, a trimmed GTFS static zip.
- Units: predictions parsing/sorting/labels, incidents filtering, positions decode (car count from `license_plate`), network building (longest shape, transfer detection), config validation, poller (cadence, demand gating, backoff, error states) with a fake clock and fake client, API responses via `TestClient`.
- Browser checks each milestone (local run against fixtures via a `--fixtures` mode, then live on the Pi): layout at 1920×1080, stale states, alert rotation, glide, phone view on a real phone.

## Milestones

1. Backend: config, client, parsing, poller, state, `/api/board` (fixtures mode for local dev).
2. Wall board page: arrivals, clock, stale pill, closed state.
3. Alerts banner.
4. Deploy: systemd unit, GitHub, kiosk-selector `metro` target, README. **Board is usable on the wall here.**
5. Live map: network endpoint, basemap extract + style, overlay, glide, landmarks.
6. Phone view + Tailscale mapping.

## Out of scope (for now)

Bus panel (designed for: a second `platforms`-like panel fed by
`NextBusService.svc/json/jPredictions`), elevator outages, crowding (the
GTFS-RT feed carries occupancy), multi-station layouts.

## Needs from Ethan

- A WMATA API key (developer.wmata.com → subscribe to the Default Tier), put in `~/wmata-board/.env` on the Pi.
- An empty private GitHub repo named `wmata-board` (or OK to install the GitHub CLI so I can create it).

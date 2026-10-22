// HTML builders shared by the wall and the phone. Strings only, no DOM, so
// they run under node --test.
import { LINE_COLORS, NOTICE_UNAVAILABLE, minuteParts, escapeHtml, waitClass, delayText } from "./format.js";

export function chip(line, cls = "chip") {
  const [bg, fg] = LINE_COLORS[line] || ["#3b4a5e", "#fff"];
  return `<span class="${cls}" style="background:${bg};color:${fg}">${escapeHtml(line)}</span>`;
}

function rowHtml(t) {
  const m = minuteParts(t.display);
  const cars = t.cars ? `${escapeHtml(String(t.cars))} car` : "";
  const unit = m.unit ? `<small>${m.unit}</small>` : "";
  return `<div class="row">${chip(t.line)}` +
    `<span class="dest">${escapeHtml(t.destination)}<span class="cars">${cars}</span></span>` +
    `<span class="min${m.now ? " now" : ""}">${escapeHtml(m.big)}${unit}</span></div>`;
}

export function arrivalsHtml(board) {
  if (board.notice) return `<div class="notice">${escapeHtml(board.notice)}</div>`;
  return board.platforms.map(p =>
    `<section class="plat"><h2>${escapeHtml(p.label)}</h2>` +
    (p.trains.length ? p.trains.map(rowHtml).join("") : `<div class="row empty">No trains predicted</div>`) +
    `</section>`).join("");
}

// Arrivals panel; `expired` swaps the rows for the "unavailable" notice (see arrivalsExpired).
export function arrivalsPanelHtml(board, expired) {
  return arrivalsHtml(expired ? { ...board, notice: NOTICE_UNAVAILABLE } : board);
}

export function alertHtml(alert) {
  return `<span class="tag">ALERT</span>` +
    `<span class="achips">${alert.lines.map(l => chip(l, "chip sm")).join("")}</span>` +
    `<span class="atext">${escapeHtml(alert.text)}</span>`;
}

// ---- commute panel (wall + phone) ----------------------------------------

const wait = m => `<span class="cw ${waitClass(m)}">${m}<small>min</small></span>`;
const sched = live => live ? "" : `<span class="sched">sched</span>`;
const cnotice = text => `<div class="crow cempty">${escapeHtml(text)}</div>`;

function cbody(c, rows, head, row, empty) {
  if (c.notice) return cnotice(c.notice);
  if (!rows.length) return cnotice(empty);
  return head + rows.map((r, i) => row(r, i)).join("");
}

// data-i: the phone opens a row's trip card by index.
function amRow(r, i) {
  const cls = r.target ? " target" : "";
  return `<div data-i="${i}" class="crow am${cls}">${chip(r.line)}<span class="ct">${escapeHtml(r.leave)}</span>${wait(r.mc_wait)}` +
    `<span class="ct dim">${escapeHtml(r.brookland)}</span>` +
    `<span class="cs">${escapeHtml(r.shuttle)}<small>+${r.spare}</small></span>${sched(r.live)}</div>`;
}

function amStationRow(r, i) {
  return `<div data-i="${i}" class="crow am station">${chip(r.line)}<span class="ct">${escapeHtml(r.leave)}</span>` +
    `${wait(r.mc_wait)}<span class="ct dim">${escapeHtml(r.red_leave)}</span>` +
    `<span class="ct">${escapeHtml(r.arrive)}</span>${sched(r.live)}</div>`;
}

// Hospital/station switch: `attr` is data-dest (morning) or data-origin (evening).
function ctabs(attr, chosen, hospital, station) {
  const tab = (key, label) =>
    `<button class="ctab${(key === "station") === (chosen === "station") ? " on" : ""}" data-${attr}="${key}">${escapeHtml(label)}</button>`;
  return `<div class="ctabs">${tab("hospital", hospital)}${tab("station", station || "Station")}</div>`;
}

// Wall: commuteAmHtml(c), the hospital only. Phone: with tabs, and dest "station" for Takoma.
export function commuteAmHtml(c, dest = "hospital", { tabs = false } = {}) {
  const am = c.am || { shuttles: [], rows: [], station: [], station_name: "" };
  const toStation = tabs && dest === "station";
  const shuttles = am.shuttles.length ? ` · shuttle ${am.shuttles.map(escapeHtml).join(" / ")}` : "";
  const title = !tabs ? `${escapeHtml(c.name)}${shuttles}` : `To work${toStation ? "" : shuttles}`;
  const head = toStation
    ? `<div class="crow am station chead"><span></span><span>Leave</span><span>Metro Ctr wait</span>` +
      `<span>Red</span><span>${escapeHtml(am.station_name || "Arrive")}</span><span></span></div>`
    : `<div class="crow am chead"><span></span><span>Leave</span><span>Metro Ctr wait</span>` +
      `<span>Brookland</span><span class="r">Shuttle</span><span></span></div>`;
  return `<section class="commute"><h2>${title}</h2>` +
    (tabs ? ctabs("dest", dest, c.name, am.station_name) : "") +
    cbody(c, toStation ? am.station || [] : am.rows, head, toStation ? amStationRow : amRow, "No connections found") +
    `</section>`;
}

// Phone, when the panel was opened with the Commute button: pick the direction.
export function commuteModeHtml(mode) {
  const tab = (key, label) => `<button class="ctab${key === mode ? " on" : ""}" data-mode="${key}">${label}</button>`;
  return `<div class="ctabs cmode">${tab("am", "Morning")}${tab("pm", "Evening")}</div>`;
}

function homeTail(r) {
  return `${wait(r.mc_wait)}${chip(r.line)}<span class="ct">${escapeHtml(r.home)}</span>${sched(r.live)}`;
}

export function commutePmHtml(c, origin) {
  const pm = c.pm || { hospital: [], station: [], station_name: "" };
  const fromStation = origin === "station";
  const head = fromStation
    ? `<div class="crow pm station chead"><span>Red</span><span>Metro Ctr wait</span><span></span><span>Home</span><span></span></div>`
    : `<div class="crow pm chead"><span>Shuttle</span><span>Red</span><span>Metro Ctr wait</span><span></span><span>Home</span><span></span></div>`;
  const row = fromStation
    ? (r, i) => `<div data-i="${i}" class="crow pm station"><span class="ct">${escapeHtml(r.red_leave)}</span>${homeTail(r)}</div>`
    : (r, i) => `<div data-i="${i}" class="crow pm"><span class="ct">${escapeHtml(r.shuttle)}</span>` +
        `<span class="ct dim">${escapeHtml(r.red_leave)}</span>${homeTail(r)}</div>`;
  return `<section class="commute"><h2>Home · from</h2>` +
    ctabs("origin", origin, "Hospital", pm.station_name) +
    cbody(c, fromStation ? pm.station : pm.hospital, head, row, "No connections found") + `</section>`;
}

// ---- trip cards (phone: tap a map train or a commute row) -------------------

const TRIP_STOPS = 5;

// The stops to show: from..to inclusive for a commute leg, else the next few.
function legStops(stops, from, to) {
  if (!from) return stops.slice(0, TRIP_STOPS);
  const a = stops.findIndex(s => s.code === from);
  const b = stops.findIndex(s => s.code === to);
  return stops.slice(Math.max(0, a), b >= 0 ? b + 1 : undefined);
}

function tripHead(line, title, meta) {
  return `<div class="thead">${chip(line)}<span class="tdest">${escapeHtml(title)}</span></div>` +
    (meta.length ? `<div class="tmeta">${meta.map(escapeHtml).join(" · ")}</div>` : "");
}

// One train: line, destination, cars, live/sched, delay, and its stops.
export function tripHtml(trip, { from = null, to = null } = {}) {
  const meta = [];
  if (trip.cars) meta.push(`${trip.cars} cars`);
  const late = delayText(trip.delay_s);
  if (late) meta.push(late);
  meta.push(trip.live ? "live" : "timetable");
  const stops = legStops(trip.stops, from, to);
  const ends = new Set([from, to]);
  return `<section class="trip">${tripHead(trip.line, trip.destination ? `To ${trip.destination}` : "Train", meta)}` +
    (stops.length
      ? `<div class="tstops">${stops.map(s => `<div class="tstop${ends.has(s.code) ? " end" : ""}">` +
          `<span>${escapeHtml(s.name)}</span><span class="ttime">${escapeHtml(s.time ?? "—")}</span></div>`).join("")}</div>`
      : `<div class="tnone">No upcoming stops</div>`) + `</section>`;
}

// Map tap: `trip` is null when its predictions couldn't be found.
export function trainCardHtml(train, trip) {
  if (trip) return tripHtml(trip);
  const meta = train.cars ? [`${train.cars} cars`] : [];
  return `<section class="trip">${tripHead(train.line, "Train", meta)}` +
    `<div class="tnone">No stop predictions for this train</div></section>`;
}

const step = text => `<div class="tstep">${escapeHtml(text)}</div>`;

function legHtml(leg, trip) {
  if (trip === undefined) return `<section class="trip">${tripHead(leg.line, "Loading…", [])}</section>`;
  if (trip === null) return `<section class="trip">${tripHead(leg.line, "Train", [])}` +
    `<div class="tnone">Details unavailable</div></section>`;
  return tripHtml(trip, { from: leg.from, to: leg.to });
}

// Commute row tap: both legs in full, with the transfer and shuttle between.
// kind: "am" | "am-station" | "hospital" | "station"; trips[i]: undefined loading, null failed.
export function commuteCardHtml(row, kind, trips, stationName = "Takoma") {
  const [a, b] = row.legs;
  const parts = [];
  if (kind === "am") parts.push(`<h3>Leave ${escapeHtml(row.leave)} → shuttle ${escapeHtml(row.shuttle)}</h3>`);
  else if (kind === "am-station") parts.push(`<h3>Leave ${escapeHtml(row.leave)} → ${escapeHtml(stationName)} ${escapeHtml(row.arrive)}</h3>`);
  else if (kind === "hospital") {
    parts.push(`<h3>Shuttle ${escapeHtml(row.shuttle)} → home ${escapeHtml(row.home)}</h3>`);
    parts.push(step(`Shuttle ${row.shuttle} → Brookland ${row.brookland}`));
  } else parts.push(`<h3>Red ${escapeHtml(row.red_leave)} → home ${escapeHtml(row.home)}</h3>`);
  parts.push(legHtml(a, trips[0]));
  parts.push(step(`Metro Center · ${row.mc_wait} min wait`));
  parts.push(legHtml(b, trips[1]));
  if (kind === "am") parts.push(step(`Brookland ${row.brookland} → shuttle ${row.shuttle} (+${row.spare})`));
  return parts.join("");
}

// ---- station picker (phone) ------------------------------------------------

// Lowercase words with accents and punctuation gone: "L'Enfant" and a phone's
// curly "L’enfant" both become "lenfant"; "Foggy Bottom-GWU" is three words.
const searchWords = text => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
  .replace(/['\u2018\u2019`.]/g, "").split(/[^a-z0-9]+/).filter(Boolean);

// Spelled-out words for WMATA's abbreviated names, and the other names people use.
const EXPAND = { st: "street", av: "avenue", sq: "square", rd: "road", mt: "mount", u: "university" };
const ALIASES = {
  "Gallery Place": "chinatown", "Navy Yard-Ballpark": "nationals park", "Stadium-Armory": "rfk",
  "Ronald Reagan Washington National Airport": "dca national airport",
  "Washington Dulles International Airport": "iad dulles", "Smithsonian": "mall",
  "Hyattsville Crossing": "prince georges plaza", "Federal Center SW": "southwest",
};
function stationWords(name) {
  const words = searchWords(name);
  return [...words, ...words.map(w => EXPAND[w]).filter(Boolean), ...searchWords(ALIASES[name] ?? "")];
}

// Stations matching `query`: every word typed starts a word of the name (or an
// alias), or the whole query, spaces and punctuation ignored, is inside the
// name ("lenf", "l enfant", "gallery", "chinatown", "king street"). Names that
// start with it first, then the rest; alphabetical within each.
export function matchStations(stations, query) {
  const q = searchWords(query);
  const byName = (a, b) => a.name.localeCompare(b.name);
  if (!q.length) return [...stations].sort(byName);
  const joined = q.join("");
  const rank = s => {
    const words = stationWords(s.name), flat = searchWords(s.name).join("");
    if (flat.startsWith(joined)) return 0;
    if (q.every(w => words.some(n => n.startsWith(w))) || flat.includes(joined)) return 1;
    return -1;
  };
  return stations.map(s => [rank(s), s]).filter(([r]) => r >= 0)
    .sort(([ra, a], [rb, b]) => ra - rb || byName(a, b)).map(([, s]) => s);
}

// The nearest station to lon/lat (an equirectangular distance is plenty here).
export function nearestStation(stations, lon, lat) {
  const k = Math.cos(lat * Math.PI / 180);
  let best = null, bestD = Infinity;
  for (const s of stations) {
    const d = ((s.lon - lon) * k) ** 2 + (s.lat - lat) ** 2;
    if (d < bestD) { best = s; bestD = d; }
  }
  return best;
}

// One row per station: its name (picks it) and a star (favorites it).
// `favs`: the favorite stations' first codes.
export function stationRowsHtml(stations, current, favs = []) {
  if (!stations.length) return `<div class="tnone">No matching station</div>`;
  return stations.map(s => {
    const code = escapeHtml(s.codes[0]), fav = favs.includes(s.codes[0]);
    return `<div class="prow${s.codes.includes(current) ? " on" : ""}">` +
      `<button class="pname" data-code="${code}">${escapeHtml(s.name)}</button>` +
      `<button class="pstar${fav ? " fav" : ""}" data-fav="${code}" aria-label="${fav ? "Unfavorite" : "Favorite"}">${fav ? "★" : "☆"}</button></div>`;
  }).join("");
}

// The picker's list: favorites first (when not searching), then every match.
export function pickerListHtml(stations, query, current, favs = []) {
  const found = matchStations(stations, query);
  const favorites = favs.map(c => stations.find(s => s.codes[0] === c)).filter(Boolean);
  if (query.trim() || !favorites.length) return stationRowsHtml(found, current, favs);
  return `<div class="phead">Favorites</div>${stationRowsHtml(favorites, current, favs)}` +
    `<div class="phead">All stations</div>${stationRowsHtml(found, current, favs)}`;
}

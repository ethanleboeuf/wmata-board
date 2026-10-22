// Phone view: full-screen pannable map + draggable bottom sheet with arrivals
// and every alert (no rotation -- there's room to list them). Tapping a train
// on the map or a commute row opens a trip card.
import { formatClock, pillState, arrivalsExpired, mergeAlerts, ridePlan, escapeHtml } from "./format.js";
import { arrivalsPanelHtml, alertHtml, commuteAmHtml, commutePmHtml, commuteModeHtml, trainCardHtml,
         commuteCardHtml, matchStations, nearestStation, stationRowsHtml } from "./render.js";
import { createMap } from "./map.js";
import { startCommute, tripQuery } from "./commute.js";

const $ = id => document.getElementById(id);
const startMs = Date.now();
let board = null, lastOkMs = null, version = null;
// The station the arrivals are for: null is home (Court House), where every
// launch starts; else {codes, name} from the picker.
let away = null;

let pollTimer = null;
async function poll() {
  clearTimeout(pollTimer);   // tolerate an extra immediate call without a second chain
  const asked = away;
  try {
    const r = await fetch(`/api/board${asked ? `?station=${asked.codes[0]}` : ""}`,
                          { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (r.status === 404 && asked) { away = null; return; }   // finally{} polls home
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const body = await r.json();
    if (asked !== away) return;   // switched station while this was in flight
    board = body;
    lastOkMs = Date.now();
    if (version === null) version = board.version;
    else if (board.version !== version) { location.reload(); return; }
    $("station").innerHTML = `${escapeHtml(board.station.name)}<span class="caret">▾</span>`;
    renderArrivals(true);
    renderAlerts();
  } catch (err) {
    console.warn("board poll failed", err);
  } finally {
    pollTimer = setTimeout(poll, 5000);
  }
}

// Re-rendered on a new board, or when the local 10-minute expiry flips.
let shownExpired = null;
function renderArrivals(force = false) {
  if (!board) return;
  const expired = arrivalsExpired({ nowMs: Date.now(), lastOkMs, arrivalsAgeS: board.freshness?.arrivals?.age_s ?? null });
  if (!force && expired === shownExpired) return;
  shownExpired = expired;
  $("arrivals").innerHTML = arrivalsPanelHtml(board, expired);
}

// Commute card at the top of the sheet during the morning/evening windows, or
// any time via the Commute button (`manual`: "am" | "pm", with a switch between
// them). The button also hides an automatic panel, until the page reloads. The
// hospital/Takoma choices (morning `dest`, evening `origin`) are remembered here.
const stored = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } };
const store = (key, value) => { try { localStorage.setItem(key, value); } catch { /* not remembered, still switched */ } };
let commute = null, manual = null, hidden = false;
let origin = stored("commuteFrom", "hospital"), dest = stored("commuteTo", "hospital");
const commuteShown = () => !!commute && !hidden;
function renderCommute() {
  const el = $("commute");
  $("cbtn").classList.toggle("on", commuteShown());
  if (!commuteShown()) { el.innerHTML = ""; return; }
  el.innerHTML = (manual ? commuteModeHtml(commute.mode) : "") +
    (commute.mode === "am" ? commuteAmHtml(commute, dest, { tabs: true }) : commutePmHtml(commute, origin));
}
$("commute").addEventListener("click", ev => {
  const row = ev.target.closest("[data-i]");
  if (row && commute) { openCommuteRow(Number(row.dataset.i)); return; }
  const tab = ev.target.closest("[data-origin], [data-dest], [data-mode]");
  if (!tab) return;
  if (tab.dataset.mode) {
    if (tab.dataset.mode !== commute?.mode) { manual = tab.dataset.mode; commutePoller.poll(); }
    return;
  }
  if (tab.dataset.origin) store("commuteFrom", origin = tab.dataset.origin);
  else store("commuteTo", dest = tab.dataset.dest);
  renderCommute();
});
$("cbtn").addEventListener("click", () => {
  if (commuteShown()) {
    if (manual) { manual = null; commute = null; } else hidden = true;
  } else {
    hidden = false;
    if (!commute) manual = new Date().getHours() < 12 ? "am" : "pm";
  }
  renderCommute();
  renderAlerts();
  commutePoller.poll();
});
const commutePoller = startCommute(c => { commute = c; renderCommute(); renderAlerts(); }, () => manual);

// The board's alerts, plus (while the commute card is up) Red line ones.
function renderAlerts() {
  $("alerts").innerHTML = mergeAlerts(board?.alerts, commuteShown() ? commute.alerts : null)
    .map(a => `<div class="alert">${alertHtml(a)}</div>`).join("");
}

// ---- trip card: one floating card, refreshed while open ----
// A card for a known train has an "I'm on this one" button: that trip (a
// commute row: both, switching at Metro Center) gets a little rider on every
// map -- the ride lives on the server (/api/ride), so the wall shows it too.
const CARD_REFRESH_MS = 15000;
let card = null;   // {legs, load: async () => html, html, trips} while open
let ride = null;   // the server's current ride, refreshed with each card
async function rideApi(method = "GET", body) {
  try {
    const r = await fetch("/api/ride", { method, cache: "no-store", signal: AbortSignal.timeout(8000),
      headers: body ? { "Content-Type": "application/json" } : {}, body: body && JSON.stringify(body) });
    if (r.ok) ride = (await r.json()).ride;
  } catch { /* keep what we had */ }
}
async function fetchTrip(id) {
  try {
    const r = await fetch(`/api/trip/${encodeURIComponent(id)}${tripQuery()}`,
                          { cache: "no-store", signal: AbortSignal.timeout(8000) });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
function rideButton() {
  if (!card?.legs.length) return "";
  const on = !!ride && ride.trips.join() === card.legs.map(l => l.trip).join();
  return `<button class="tride${on ? " on" : ""}">${on ? "🙋 Riding along · hop off" : "🙋 I'm on this one"}</button>`;
}
function showCard(html) {
  if (card) card.html = html;
  $("card").innerHTML = `<button class="tclose" aria-label="Close">✕</button>${html}${rideButton()}`;
  $("card").hidden = false;
}
async function toggleRide() {
  const shown = card, on = $("card").querySelector(".tride.on");
  if (on) await rideApi("DELETE");
  else await rideApi("PUT", ridePlan(shown.legs, shown.trips || [], Date.now() / 1000));
  if (card === shown) showCard(shown.html);
}
async function openCard(next) {
  card = next;
  showCard(next.loading);
  while (card === next) {
    const [html] = await Promise.all([next.load(), rideApi()]);
    if (card !== next) return;
    showCard(html);
    await new Promise(res => setTimeout(res, CARD_REFRESH_MS));
  }
}
function closeCard() { card = null; $("card").hidden = true; }
$("card").addEventListener("click", ev => {
  if (ev.target.closest(".tclose")) closeCard();
  else if (ev.target.closest(".tride")) toggleRide();
});

function openTrain(train) {
  const next = {
    legs: train.trip_id ? [{ trip: train.trip_id, to: null }] : [],
    loading: trainCardHtml(train, null).replace("No stop predictions for this train", "Loading…"),
    load: async () => {
      next.trips = [train.trip_id ? await fetchTrip(train.trip_id) : null];
      return trainCardHtml(train, next.trips[0]);
    },
  };
  openCard(next);
}
function openCommuteRow(i) {
  const kind = commute.mode === "am" ? (dest === "station" ? "am-station" : "am")
    : origin === "station" ? "station" : "hospital";
  const rows = { am: commute.am?.rows, "am-station": commute.am?.station,
                 station: commute.pm?.station, hospital: commute.pm?.hospital }[kind];
  const row = rows?.[i];
  if (!row?.legs) return;
  const name = commute.am?.station_name;
  const next = {
    legs: row.legs,
    loading: commuteCardHtml(row, kind, [undefined, undefined], name),
    load: async () => {
      next.trips = await Promise.all(row.legs.map(l => fetchTrip(l.trip)));
      return commuteCardHtml(row, kind, next.trips, name);
    },
  };
  openCard(next);
}

// ---- station picker: tap the station name ----
let stations = null, home = "K01";   // from /api/network (home: the wall's station), loaded on first open
async function loadStations() {
  if (!stations) {
    try {
      const r = await fetch("/api/network", { signal: AbortSignal.timeout(8000) });
      if (r.ok) ({ stations, home } = await r.json());
    } catch { /* retried on the next open */ }
  }
  return stations;
}
function renderPicker(note = "") {
  const query = $("psearch")?.value ?? "";
  const current = board?.station.code;
  if (!$("psearch")) {
    $("picker").innerHTML = `<button class="tclose" aria-label="Close">✕</button><h3>Arrivals at</h3>` +
      `<div class="pbtns"><button class="ctab" data-near>📍 Nearest</button>` +
      `<button class="ctab" data-home>🏠 Court House</button></div>` +
      `<input id="psearch" type="search" placeholder="Search stations" autocomplete="off">` +
      `<div id="pnote" class="tnone"></div><div id="plist" class="plist"></div>`;
  }
  $("pnote").textContent = note;
  $("plist").innerHTML = stations ? stationRowsHtml(matchStations(stations, query), current)
                                  : `<div class="tnone">Stations unavailable</div>`;
}
async function openPicker() {
  closeCard();
  $("picker").innerHTML = "";
  $("picker").hidden = false;
  renderPicker("Loading…");
  await loadStations();
  if (!$("picker").hidden) renderPicker();
}
const closePicker = () => { $("picker").hidden = true; };
let mapRef = null;
function chooseStation(s) {
  closePicker();
  away = !s || s.codes.includes(home) ? null : { codes: s.codes, name: s.name };
  board = null;
  $("station").innerHTML = `${escapeHtml(s ? s.name : "Court House")}<span class="caret">▾</span>`;
  $("arrivals").innerHTML = `<div class="notice">Loading arrivals…</div>`;
  poll();
  if (!away) recenter?.();
  else mapRef?.flyTo({ center: [s.lon, s.lat], zoom: Math.max(mapRef.getZoom(), 12.5), duration: 800 });
}
$("station").addEventListener("click", openPicker);
// The page itself never scrolls; focusing a button in the half-hidden sheet
// would otherwise scroll the (overflow: hidden) body to bring it into view.
document.body.addEventListener("scroll", () => { document.body.scrollTop = 0; });
$("picker").addEventListener("input", () => renderPicker());
$("picker").addEventListener("click", async ev => {
  if (ev.target.closest(".tclose")) closePicker();
  else if (ev.target.closest("[data-home]")) chooseStation(null);
  else if (ev.target.closest("[data-code]")) {
    const code = ev.target.closest("[data-code]").dataset.code;
    chooseStation(stations.find(s => s.codes.includes(code)));
  } else if (ev.target.closest("[data-near]")) {
    if (!stations || !navigator.geolocation) { renderPicker("Location unavailable"); return; }
    renderPicker("Finding you…");
    navigator.geolocation.getCurrentPosition(
      pos => chooseStation(nearestStation(stations, pos.coords.longitude, pos.coords.latitude)),
      () => renderPicker("Location unavailable — allow it in Settings, or search"),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
  }
});

// Coming back from the background: don't show a false red "Board offline" while
// waiting out the rest of the poll interval.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") { poll(); commutePoller.poll(); }
});

function tick() {
  const now = Date.now();
  $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
  const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
  const pill = $("pill");
  pill.hidden = p.kind === "hidden";
  pill.className = `pill ${p.kind}`;
  pill.textContent = p.text;
  renderArrivals();
}

// Bottom sheet: drag the handle or header between "peek" (38% visible) and "open"
// (85%); a tap on either toggles. Sized in px from innerHeight so CSS and JS agree.
const sheet = $("sheet");
const sheetH = () => Math.round(innerHeight * 0.85);
const PEEK = () => sheetH() - Math.round(innerHeight * 0.38);
let offset = PEEK(), drag = null;
const place = y => {
  offset = Math.max(0, Math.min(PEEK(), y));
  sheet.style.height = `${sheetH()}px`;
  sheet.style.transform = `translateY(${offset}px)`;
};
function endDrag() {
  if (!drag) return;
  const moved = Math.abs(offset - drag.offset) > 5;
  sheet.classList.remove("dragging");
  place(moved ? (offset < PEEK() / 2 ? 0 : PEEK()) : (drag.offset === 0 ? PEEK() : 0));
  drag = null;
}
for (const el of [$("handle"), document.querySelector(".shdr")]) {
  el.addEventListener("pointerdown", ev => {
    if (ev.target.closest("button")) return;   // the station name opens the picker instead
    drag = { y: ev.clientY, offset };
    sheet.classList.add("dragging");
    ev.currentTarget.setPointerCapture(ev.pointerId);
  });
  el.addEventListener("pointermove", ev => { if (drag) place(drag.offset + ev.clientY - drag.y); });
  el.addEventListener("pointerup", endDrag);
  el.addEventListener("pointercancel", endDrag);
  el.addEventListener("lostpointercapture", endDrag);
}
addEventListener("resize", () => place(offset > 0 ? PEEK() : 0));
place(PEEK());

// Fit the wall's bbox into the part of the map the sheet doesn't cover.
const fitPadding = () => ({
  top: 56, left: 16, right: 16,
  bottom: Math.min(sheetH() - offset, innerHeight * 0.6) + 16,
});

let recenter = null;
$("recenter").addEventListener("click", () => recenter?.());
function startMap() {
  createMap($("map"), { interactive: true, fit: "contain", padding: fitPadding })
    .then(m => {
      recenter = () => m.recenter();
      mapRef = m.map;
      // Allow zooming out to the whole system, but not off into the void.
      m.map.setMaxBounds([[-77.75, 38.6], [-76.6, 39.3]]);
      m.map.setMinZoom(8.5);
      // A tap (not a pan) near a train opens its card; anywhere else closes it.
      m.map.on("click", ev => {
        const train = m.trainAt(ev.point.x, ev.point.y);
        if (train) openTrain(train); else closeCard();
      });
    })
    .catch(err => {
      console.error("map failed; retrying in 30 s", err);
      $("map").replaceChildren();
      setTimeout(startMap, 30000);
    });
}
startMap();

setInterval(tick, 1000);
tick();
poll();

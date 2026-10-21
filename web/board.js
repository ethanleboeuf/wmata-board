// Wall board: polls /api/board, renders arrivals, ticks the clock and pill.
import { formatClock, pillState, alertIndex, arrivalsExpired } from "./format.js";
import { arrivalsPanelHtml, alertHtml } from "./render.js";
import { createMap } from "./map.js";

const POLL_MS = 5000;
const $ = id => document.getElementById(id);
const stage = $("stage");

function fit() {
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
}
addEventListener("resize", fit);
fit();

const startMs = Date.now();
let board = null, lastOkMs = null, version = null;
export const hooks = { onBoard: [] };   // Task 9 subscribes the alert banner here

let pollTimer = null;
async function poll() {
  clearTimeout(pollTimer);   // tolerate an extra immediate call without a second chain
  try {
    const r = await fetch("/api/board", { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    board = await r.json();
    lastOkMs = Date.now();
    if (version === null) version = board.version;
    else if (board.version !== version) { location.reload(); return; }
    render();
  } catch (err) {
    console.warn("board poll failed", err);   // the pill turns red after OFFLINE_AFTER_MS
  } finally {
    pollTimer = setTimeout(poll, POLL_MS);
  }
}

function render() {
  $("station").textContent = board.station.name;
  document.title = board.station.name;
  renderArrivals(true);
  hooks.onBoard.forEach(fn => fn(board));
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

function tick() {
  const now = Date.now();
  $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
  const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
  const pill = $("pill");
  pill.hidden = p.kind === "hidden";
  pill.className = `pill ${p.kind}`;
  pill.textContent = p.text;
  renderArrivals();
  renderAlert();
}

let alerts = [], shownKey = null;
hooks.onBoard.push(b => { alerts = b.alerts || []; renderAlert(); });

// Several alerts rotate every 10 s; none -> no banner and the panels below
// reclaim the space (the map panel re-fits itself via its ResizeObserver).
function renderAlert() {
  const banner = $("alert");
  const i = alertIndex(alerts.length, Date.now());
  if (i < 0) { banner.hidden = true; shownKey = null; return; }
  const a = alerts[i], key = `${a.id}|${a.updated}|${a.text}`;
  if (key !== shownKey) { banner.innerHTML = alertHtml(a); shownKey = key; }
  banner.hidden = false;
}

setInterval(tick, 1000);
tick();
poll();
function startMap() {
  createMap($("map"), { interactive: false, fit: "cover" }).catch(err => {
    console.error("map failed; retrying in 30 s", err);
    $("map").replaceChildren();
    setTimeout(startMap, 30000);
  });
}
startMap();

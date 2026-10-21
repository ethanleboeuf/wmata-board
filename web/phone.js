// Phone view: full-screen pannable map + draggable bottom sheet with arrivals
// and every alert (no rotation -- there's room to list them).
import { formatClock, pillState, arrivalsExpired } from "./format.js";
import { arrivalsPanelHtml, alertHtml } from "./render.js";
import { createMap } from "./map.js";

const $ = id => document.getElementById(id);
const startMs = Date.now();
let board = null, lastOkMs = null, version = null;

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
    $("station").textContent = board.station.name;
    renderArrivals(true);
    $("alerts").innerHTML = board.alerts.map(a => `<div class="alert">${alertHtml(a)}</div>`).join("");
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

// Coming back from the background: don't show a false red "Board offline" while
// waiting out the rest of the poll interval.
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") poll(); });

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
      // Allow zooming out to the whole system, but not off into the void.
      m.map.setMaxBounds([[-77.75, 38.6], [-76.6, 39.3]]);
      m.map.setMinZoom(8.5);
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

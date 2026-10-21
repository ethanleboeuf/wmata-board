// Phone view: full-screen pannable map + draggable bottom sheet with arrivals
// and every alert (no rotation -- there's room to list them).
import { formatClock, pillState } from "./format.js";
import { arrivalsHtml, alertHtml } from "./render.js";
import { createMap } from "./map.js";

const $ = id => document.getElementById(id);
const startMs = Date.now();
let board = null, lastOkMs = null, version = null;

async function poll() {
  try {
    const r = await fetch("/api/board", { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    board = await r.json();
    lastOkMs = Date.now();
    if (version === null) version = board.version;
    else if (board.version !== version) { location.reload(); return; }
    $("station").textContent = board.station.name;
    $("arrivals").innerHTML = arrivalsHtml(board);
    $("alerts").innerHTML = board.alerts.map(a => `<div class="alert">${alertHtml(a)}</div>`).join("");
  } catch (err) {
    console.warn("board poll failed", err);
  } finally {
    setTimeout(poll, 5000);
  }
}

function tick() {
  const now = Date.now();
  $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
  const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
  const pill = $("pill");
  pill.hidden = p.kind === "hidden";
  pill.className = `pill ${p.kind}`;
  pill.textContent = p.text;
}

// Bottom sheet: drag the handle between "peek" (38vh visible) and "open" (85vh).
const sheet = $("sheet");
const PEEK = () => innerHeight * 0.85 - innerHeight * 0.38;
let offset = PEEK(), dragFrom = null;
const place = y => { offset = Math.max(0, Math.min(PEEK(), y)); sheet.style.transform = `translateY(${offset}px)`; };
$("handle").addEventListener("pointerdown", ev => {
  dragFrom = { y: ev.clientY, offset };
  sheet.classList.add("dragging");
  ev.target.setPointerCapture(ev.pointerId);
});
$("handle").addEventListener("pointermove", ev => { if (dragFrom) place(dragFrom.offset + ev.clientY - dragFrom.y); });
$("handle").addEventListener("pointerup", () => {
  if (!dragFrom) return;
  sheet.classList.remove("dragging");
  place(offset < PEEK() / 2 ? 0 : PEEK());
  dragFrom = null;
});
addEventListener("resize", () => place(offset > 0 ? PEEK() : 0));
place(PEEK());

createMap($("map"), { interactive: true, fit: "contain" })
  .then(m => {
    $("recenter").addEventListener("click", () => m.recenter());
    // Allow zooming out to the whole system, but not off into the void.
    m.map.setMaxBounds([[-77.75, 38.6], [-76.6, 39.3]]);
    m.map.setMinZoom(8.5);
  })
  .catch(err => console.error("map failed", err));

setInterval(tick, 1000);
tick();
poll();

// Split-screen tile for the kiosk's layouts: the metro board's half (both
// directions, commute panel below in the morning) or quarter (one platform).
// Fixed size, no scaling; the layout page frames it and listens for the heartbeat.
import { formatClock, pillState, alertIndex, arrivalsExpired, mergeAlerts } from "./format.js";
import { arrivalsPanelHtml, alertHtml, commuteAmHtml } from "./render.js";
import { startCommute } from "./commute.js";

export function tileOptions(search) {
  const q = new URLSearchParams(search);
  const size = q.get("size") === "quarter" ? "quarter" : "half";
  return { size, platform: size === "quarter" ? q.get("platform") || null : null };
}

// Quarter: just the platform's group (no platform given: everything).
export function tileBoard(board, { size, platform }) {
  if (size !== "quarter" || !platform) return board;
  return { ...board, platforms: board.platforms.filter(p => p.group === platform) };
}

export const showCommute = (commute, { size }) => size === "half" && commute?.mode === "am";

if (typeof document !== "undefined") {
  const POLL_MS = 5000;
  const opts = tileOptions(location.search);
  const $ = id => document.getElementById(id);
  $("stage").className = opts.size;

  const startMs = Date.now();
  let board = null, lastOkMs = null, version = null, commute = null;
  let shownExpired = null, alerts = [], shownKey = null;

  const expired = () => arrivalsExpired({ nowMs: Date.now(), lastOkMs, arrivalsAgeS: board.freshness?.arrivals?.age_s ?? null });

  function renderArrivals() {
    if (!board) return;
    const b = tileBoard(board, opts), exp = expired();
    shownExpired = exp;
    $("station").textContent = opts.size === "quarter" && b.platforms.length === 1 ? b.platforms[0].label : board.station.name;
    $("arrivals").classList.toggle("with-commute", showCommute(commute, opts));
    $("arrivals").innerHTML = arrivalsPanelHtml(b, exp) + (showCommute(commute, opts) ? commuteAmHtml(commute) : "");
  }

  function updateAlerts() {
    alerts = mergeAlerts(board?.alerts, showCommute(commute, opts) ? commute.alerts : null);
    renderAlert();
  }

  function renderAlert() {
    const banner = $("alert");
    const i = alertIndex(alerts.length, Date.now());
    if (i < 0) { banner.hidden = true; shownKey = null; return; }
    const a = alerts[i], key = `${a.id}|${a.updated}|${a.text}`;
    if (key !== shownKey) { banner.innerHTML = alertHtml(a); shownKey = key; }
    banner.hidden = false;
  }

  async function poll() {
    try {
      const r = await fetch("/api/board", { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      board = await r.json();
      lastOkMs = Date.now();
      if (version === null) version = board.version;
      else if (board.version !== version) { location.reload(); return; }
      renderArrivals();
      updateAlerts();
      // Success path only: fresh data, not the "unavailable" notice.
      if (!expired()) window.parent.postMessage({ kioskTile: "alive" }, "*");
    } catch (err) {
      console.warn("board poll failed", err);
    } finally {
      setTimeout(poll, POLL_MS);
    }
  }

  function tick() {
    const now = Date.now();
    $("clock").textContent = formatClock(new Date(now), board?.timezone || "America/New_York");
    const p = pillState({ nowMs: now, lastOkMs, startMs, arrivalsAgeS: board?.freshness?.arrivals?.age_s ?? null });
    $("pill").hidden = p.kind === "hidden";
    $("pill").className = `pill ${p.kind}`;
    $("pill").textContent = p.text;
    if (board && expired() !== shownExpired) renderArrivals();
    renderAlert();
  }

  if (opts.size === "half") startCommute(c => { commute = c; renderArrivals(); updateAlerts(); });
  setInterval(tick, 1000);
  tick();
  poll();
}

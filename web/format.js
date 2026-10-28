// Pure helpers shared by the wall board and the phone view (node --test).

export const LINE_COLORS = {
  RD: ["#c80f2d", "#fff"], OR: ["#ed8b00", "#111"], SV: ["#919d9d", "#111"],
  BL: ["#009cde", "#fff"], GR: ["#00b140", "#fff"], YL: ["#ffd100", "#111"],
};
export const LINE_LETTER = { RD: "R", OR: "O", SV: "S", BL: "B", GR: "G", YL: "Y" };
export const OFFLINE_AFTER_MS = 15000;
export const STALE_AFTER_S = 60;
export const UNAVAILABLE_AFTER_S = 600;
export const NOTICE_UNAVAILABLE = "Live arrivals unavailable";

export function minuteParts(display) {
  if (display === "BRD" || display === "ARR") return { big: display, unit: "", now: true };
  if (/^\d+$/.test(display ?? "")) return { big: display, unit: "min", now: false };
  return { big: "—", unit: "", now: false };
}

// Header pill: hidden when fresh, amber when the arrivals are old, red when
// the browser can't reach the board's own backend at all.
export function pillState({ nowMs, lastOkMs, startMs, arrivalsAgeS }) {
  const since = lastOkMs ?? startMs;
  if (nowMs - since > OFFLINE_AFTER_MS) return { kind: "red", text: "Board offline" };
  if (lastOkMs !== null && arrivalsAgeS !== null && arrivalsAgeS !== undefined) {
    const age = arrivalsAgeS + (nowMs - lastOkMs) / 1000;
    if (age > STALE_AFTER_S) return { kind: "amber", text: `Updated ${Math.max(1, Math.floor(age / 60))} min ago` };
  }
  return { kind: "hidden", text: "" };
}

// The server swaps 10-minute-old arrivals for a notice, but if the backend is
// down the page keeps its last board; apply the same rule locally.
export function arrivalsExpired({ nowMs, lastOkMs, arrivalsAgeS }) {
  if (lastOkMs === null || lastOkMs === undefined || arrivalsAgeS === null || arrivalsAgeS === undefined) return false;
  return arrivalsAgeS + (nowMs - lastOkMs) / 1000 > UNAVAILABLE_AFTER_S;
}

// The map overlay's corner label.
export function liveLabel({ stale, count }) {
  return stale ? "POSITIONS STALE" : `LIVE · ${count} TRAINS`;
}

const clockFormats = new Map();
export function formatClock(date, timeZone) {
  if (!clockFormats.has(timeZone)) {
    clockFormats.set(timeZone, new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", timeZone }));
  }
  // Newer ICU puts a narrow no-break space before AM/PM; normalize it.
  return clockFormats.get(timeZone).format(date).replace(/[  ]/g, " ");
}

export function alertIndex(count, nowMs, periodMs = 10000) {
  return count ? Math.floor(nowMs / periodMs) % count : -1;
}

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ESC[c]);
}

// Commute panel: how a Metro Center wait reads at a glance.
export function waitClass(minutes) {
  if (minutes <= 3) return "w-short";
  if (minutes >= 7) return "w-long";
  return "w-mid";
}

// The commute panel goes away if the backend hasn't answered for this long:
// its rows are "trains from now on", and old ones would list trains long gone.
export const COMMUTE_EXPIRE_MS = 120000;

// The board's alerts (Orange/Silver) plus the commute panel's (which adds Red),
// each incident once.
export function mergeAlerts(boardAlerts, commuteAlerts) {
  const seen = new Set(), out = [];
  for (const a of [...(boardAlerts || []), ...(commuteAlerts || [])]) {
    if (!seen.has(a.id)) { seen.add(a.id); out.push(a); }
  }
  return out;
}

// Trip card: how far off the timetable a train is ("" when unknown).
export function delayText(delayS) {
  if (delayS === null || delayS === undefined) return "";
  const m = Math.round(Math.abs(delayS) / 60);
  if (m === 0) return "On time";
  return `${m} min ${delayS > 0 ? "late" : "early"}`;
}

// ---- easter egg: "I'm on this one" puts a little rider on her train ---------

// Sent to PUT /api/ride; the server says which trip she's on (ride.py), and
// every map draws the rider on it.
export const RIDE_MAX_S = 3 * 3600;
const stopT = (trip, code) => trip?.stops?.find(s => s.code === code)?.t;

// Where a map train (no `to`) drops her: the first stop she'd get off at now
// (the server marks them `off`), else the end of its run.
const offT = trip => (trip?.stops?.find(s => s.off && s.t) ?? trip?.stops?.at(-1))?.t;

// A ride from a card's legs ([{trip, to}]) and their fetched trips (null when a
// fetch failed), in epoch seconds. It switches trains when the first reaches
// the transfer (now, if it already has), and ends 2 min after the last leg arrives.
export function ridePlan(legs, trips, nowS) {
  const first = trips[0], last = trips[legs.length - 1];
  const transfer = legs.length > 1 && first ? (stopT(first, legs[0].to) ?? nowS) : null;
  const to = legs.at(-1)?.to;
  const end = !legs.length ? null : to ? stopT(last, to) : offT(last);
  return {
    trips: legs.map(l => l.trip),
    switch_at: transfer,
    until: end && end + 120 > nowS ? end + 120 : nowS + RIDE_MAX_S,
  };
}

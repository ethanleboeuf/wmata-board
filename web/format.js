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

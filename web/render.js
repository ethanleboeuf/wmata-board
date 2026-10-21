// HTML builders shared by the wall and the phone. Strings only, no DOM, so
// they run under node --test.
import { LINE_COLORS, NOTICE_UNAVAILABLE, minuteParts, escapeHtml, waitClass } from "./format.js";

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
  return head + rows.map(row).join("");
}

function amRow(r) {
  const cls = r.target ? " target" : r.late ? " late" : "";
  return `<div class="crow am${cls}">${chip(r.line)}<span class="ct">${escapeHtml(r.leave)}</span>${wait(r.mc_wait)}` +
    `<span class="ct dim">${escapeHtml(r.brookland)}</span>` +
    `<span class="cs">${escapeHtml(r.shuttle)}<small>+${r.spare}</small></span>${sched(r.live)}</div>`;
}

export function commuteAmHtml(c) {
  const am = c.am || { shuttles: [], rows: [] };
  const title = `${escapeHtml(c.name)}${am.shuttles.length ? ` · shuttle ${am.shuttles.map(escapeHtml).join(" / ")}` : ""}`;
  const head = `<div class="crow am chead"><span></span><span>Leave</span><span>Metro Ctr wait</span>` +
    `<span>Brookland</span><span class="r">Shuttle</span><span></span></div>`;
  return `<section class="commute"><h2>${title}</h2>` +
    cbody(c, am.rows, head, amRow, "No connections found") + `</section>`;
}

function homeTail(r) {
  return `${wait(r.mc_wait)}${chip(r.line)}<span class="ct">${escapeHtml(r.home)}</span>${sched(r.live)}`;
}

export function commutePmHtml(c, origin) {
  const pm = c.pm || { hospital: [], station: [], station_name: "" };
  const fromStation = origin === "station";
  const tab = (key, label) =>
    `<button class="ctab${(key === "station") === fromStation ? " on" : ""}" data-origin="${key}">${escapeHtml(label)}</button>`;
  const head = fromStation
    ? `<div class="crow pm station chead"><span>Red</span><span>Metro Ctr wait</span><span></span><span>Home</span><span></span></div>`
    : `<div class="crow pm chead"><span>Shuttle</span><span>Red</span><span>Metro Ctr wait</span><span></span><span>Home</span><span></span></div>`;
  const row = fromStation
    ? r => `<div class="crow pm station"><span class="ct">${escapeHtml(r.red_leave)}</span>${homeTail(r)}</div>`
    : r => `<div class="crow pm"><span class="ct">${escapeHtml(r.shuttle)}</span>` +
        `<span class="ct dim">${escapeHtml(r.red_leave)}</span>${homeTail(r)}</div>`;
  return `<section class="commute"><h2>Home · from</h2>` +
    `<div class="ctabs">${tab("hospital", "Hospital")}${tab("station", pm.station_name || "Station")}</div>` +
    cbody(c, fromStation ? pm.station : pm.hospital, head, row, "No connections found") + `</section>`;
}

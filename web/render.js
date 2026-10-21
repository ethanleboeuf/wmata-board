// HTML builders shared by the wall and the phone. Strings only, no DOM, so
// they run under node --test.
import { LINE_COLORS, minuteParts, escapeHtml } from "./format.js";

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

export function alertHtml(alert) {
  return `<span class="tag">ALERT</span>` +
    `<span class="achips">${alert.lines.map(l => chip(l, "chip sm")).join("")}</span>` +
    `<span class="atext">${escapeHtml(alert.text)}</span>`;
}

// The weather for the walk: icon, temperature, what to bring. Pure strings;
// `weather` is the board's {temp, icon, text, hint, hints}, or null for none.
import { escapeHtml } from "./format.js";

// Header chip. The wall passes {hint: true} to add the hint beside it; the
// phone is narrow and shows just the icon and temperature.
export function weatherHeaderHtml(weather, { hint = false } = {}) {
  if (!weather) return "";
  const chip = `<span class="wx-now" title="${escapeHtml(weather.text)}">` +
    `<span class="wx-ico">${escapeHtml(weather.icon)}</span>${escapeHtml(weather.temp)}°</span>`;
  return chip + (hint && weather.hint ? `<span class="wx-hint">${escapeHtml(weather.hint)}</span>` : "");
}

// Both hints on one dim line (the phone's, under the commute panel).
export function weatherHintsHtml(weather) {
  const hints = weather?.hints ?? [];
  return hints.length ? `<div class="wx-line">${hints.map(escapeHtml).join(" · ")}</div>` : "";
}

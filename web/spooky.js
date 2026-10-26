// Halloween dress-up for the shared map, switched on by `[map] theme =
// "halloween"` in config.toml: a purple-and-orange basemap, a moon, ghosts and
// bats drifting under the lanes, a jack-o'-lantern beside home, a cobweb on the
// hospital, and the rider as a little witch (her rat too). map.js asks for
// these pieces only when the theme is on; everything else is untouched.

export const SPOOKY_LAND = "#140e1f";

const PAINT = {
  background: { "background-color": SPOOKY_LAND },
  earth: { "fill-color": SPOOKY_LAND },
  landuse: { "fill-color": "#1d1430" },
  water: { "fill-color": "#0e2420" },
  buildings: { "fill-color": "#1d1430" },
  "roads-minor": { "line-color": "#30224a" },
  "roads-major": { "line-color": "#b8581c", "line-opacity": 0.4 },
};

// Retint the Board-navy style (web/style.json) in place of a second style
// file, and give the major roads a soft orange glow underneath.
export function spookyStyle(style) {
  const layers = [];
  for (const layer of style.layers) {
    const paint = PAINT[layer.id];
    const l = paint ? { ...layer, paint: { ...layer.paint, ...paint } } : layer;
    if (layer.id === "roads-major") {
      layers.push({ ...l, id: "roads-major-glow",
        paint: { ...l.paint, "line-opacity": 0.12, "line-blur": 4,
                 "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 9, 2, 12, 5, 16, 18] } });
    }
    layers.push(l);
  }
  return { ...style, name: "Board halloween", layers };
}

// ---- drifting ghosts and bats (an HTML layer under the SVG overlay) --------
const GHOST = `<svg viewBox="0 0 40 48" width="40" height="48">` +
  `<path class="sheet" d="M4,22 C4,10 12,2 20,2 C28,2 36,10 36,22 L36,44 L31,39.5 L25.5,44 L20,39.5 L14.5,44 L9,39.5 L4,44 Z"/>` +
  `<ellipse class="hole" cx="14" cy="20" rx="2.6" ry="3.6"/><ellipse class="hole" cx="26" cy="20" rx="2.6" ry="3.6"/>` +
  `<ellipse class="hole" cx="20" cy="29.5" rx="2.4" ry="3"/></svg>`;
const WING = `<path class="wing" d="M27,14 C20,3 10,3 1,9 C6,10 8.5,13 8.5,17 C12,14 15.5,15 17.5,19 C20.5,15 24,16 27,18.5 Z"/>`;
const BAT = `<svg viewBox="0 0 60 30" width="54" height="27">` + WING +
  `<g transform="translate(60,0) scale(-1,1)">${WING}</g>` +
  `<ellipse class="body" cx="30" cy="16" rx="4.2" ry="6.2"/>` +
  `<path class="body" d="M26.6,11.5 L26.8,6.6 L28.8,9.4 L31.2,9.4 L33.2,6.6 L33.4,11.5 Z"/>` +
  `<circle class="eye" cx="28.4" cy="11.6" r=".9"/><circle class="eye" cx="31.6" cy="11.6" r=".9"/></svg>`;
// [kind, top %, seconds to cross, delay s]; negative delays start them mid-flight.
const SPOOKS = [
  ["ghost", 18, 70, -10], ["ghost", 52, 95, -55], ["ghost", 78, 80, -30],
  ["bat", 10, 26, -4], ["bat", 34, 34, -20], ["bat", 64, 30, -12],
];
const MOON = `<svg class="moon" viewBox="0 0 80 80" width="80" height="80">` +
  `<defs><radialGradient id="moonglow"><stop offset=".5" stop-color="#ffe9a8" stop-opacity=".5"/>` +
  `<stop offset="1" stop-color="#ffe9a8" stop-opacity="0"/></radialGradient></defs>` +
  `<circle cx="40" cy="40" r="40" fill="url(#moonglow)"/><circle cx="40" cy="40" r="21" fill="#f6e7b4"/>` +
  `<circle cx="33" cy="35" r="4.5" fill="#e3d091"/><circle cx="47" cy="47" r="3.2" fill="#e3d091"/>` +
  `<circle cx="45" cy="31" r="2" fill="#e3d091"/></svg>`;

export function spookLayer() {
  const div = document.createElement("div");
  div.className = "spooks";
  div.innerHTML = MOON + SPOOKS.map(([kind, top, secs, delay]) =>
    `<div class="drift ${kind}" style="top:${top}%;animation-duration:${secs}s;animation-delay:${delay}s">` +
    `<div class="sprite" style="animation-delay:${delay / 3}s">${kind === "ghost" ? GHOST : BAT}</div></div>`).join("");
  return div;
}

// ---- spooky stations (SVG strings, drawn by map.js's drawStatic) -----------
const f = n => n.toFixed(1);

export function jackOLantern(x, y) {
  return `<g transform="translate(${f(x)},${f(y)}) scale(1.2)">` +
    `<circle r="26" fill="url(#pumpglow)"/>` +
    `<path d="M-1,-10 Q0,-16 4,-16.5" fill="none" stroke="#4f8a2e" stroke-width="3.2" stroke-linecap="round"/>` +
    `<ellipse rx="13.5" ry="11" fill="#ff7a1a" stroke="${SPOOKY_LAND}" stroke-width="2.5"/>` +
    `<path d="M-4.5,-10.6 Q-8,0 -4.5,10.6 M4.5,-10.6 Q8,0 4.5,10.6" fill="none" stroke="#d65a08" stroke-width="1.3"/>` +
    `<path d="M-7.5,-1.5 L-2.8,-1.5 L-5.1,-6 Z M2.8,-1.5 L7.5,-1.5 L5.1,-6 Z M-1.2,1.6 L1.2,1.6 L0,-.8 Z" fill="#ffe066"/>` +
    `<path d="M-8,3 Q0,10.5 8,3 L5.2,4.6 L4.2,3.2 L2,5.4 L0,3.6 L-2,5.4 L-4.2,3.2 L-5.2,4.6 Z" fill="#ffe066"/></g>`;
}

// A quarter web hooked over the top-left corner of the hospital tile at (x, y).
export function cobweb(x, y) {
  const cx = x - 15, cy = y - 15, out = [];
  const angs = [0, 30, 60, 90].map(a => a * Math.PI / 180);
  for (const a of angs) out.push(`M${f(cx)},${f(cy)} L${f(cx + 19 * Math.cos(a))},${f(cy + 19 * Math.sin(a))}`);
  const at = (r, a) => `${f(cx + r * Math.cos(a))},${f(cy + r * Math.sin(a))}`;
  for (const r of [6.5, 12, 17]) {   // threads sag toward the corner between spokes
    let d = `M${at(r, angs[0])}`;
    for (let i = 1; i < angs.length; i++) d += ` Q${at(r * 0.78, (angs[i - 1] + angs[i]) / 2)} ${at(r, angs[i])}`;
    out.push(d);
  }
  return `<path class="cobweb" d="${out.join(" ")}"/>`;
}

// ---- the rider, dressed as a witch ------------------------------------------
// Same pose and rat as map.js's RIDER: a black dress, a pointy purple hat with
// an orange band, sitting on a little broom; the rat gets a hat of its own.
export const WITCH = `<g transform="scale(2.4) translate(-1.2,4.2)"><g class="bob">` +
  `<path class="broomstick" d="M7.5,-10.6 L-9.5,-12"/>` +
  `<path class="bristles" d="M-8.6,-13.6 L-8.6,-10.4 L-15,-8.8 Q-16.2,-12.2 -15.2,-15.4 Z"/>` +
  `<path class="broomtie" d="M-9.6,-13.8 L-9.6,-10.2"/>` +
  `<path class="hair" d="M-5.4,-26 C-5.6,-20 -6.4,-17.5 -4.2,-16.4 L4.2,-16.4 C6.4,-17.5 5.6,-20 5.4,-26 A5.4,5.6 0 0 0 -5.4,-26 Z"/>` +
  `<path class="skin" d="M-2.6,-12 L-3.2,-8.6 M2.6,-12 L3.2,-8.6 M-2,-18.6 L-5.6,-12.6"/>` +
  `<path class="wave skin" d="M2,-18.6 L6.6,-23.4"/>` +
  `<path class="robe" d="M0,-19.6 L-5.4,-11 L5.4,-11 Z"/>` +
  `<circle class="face" cx="0" cy="-24.6" r="3.6"/>` +
  `<circle class="eye" cx="-1.3" cy="-24.4" r=".42"/><circle class="eye" cx="1.3" cy="-24.4" r=".42"/>` +
  `<path class="smile" d="M-1,-22.7 Q0,-21.9 1,-22.7"/>` +
  `<path class="hat" d="M-4.4,-27.6 Q-2,-32.5 .4,-36.6 Q2.4,-39.4 5.6,-38.4 Q2.8,-37.4 2.2,-34.6 L4.4,-27.6 Z"/>` +
  `<path class="hatband" d="M-4.3,-27.8 L4.3,-27.8 L3.8,-29.6 L-3.5,-29.6 Z"/>` +
  `<ellipse class="hat" cx="0" cy="-27.3" rx="7.4" ry="1.5"/>` +
  `</g><g class="rat" transform="translate(-0.4,1) translate(6,-8) scale(1.5) translate(-6,8)">` +
  `<path class="tail" d="M3.6,-9.4 Q1.6,-7.6 3.2,-6.2 Q4.6,-5.2 3.6,-4"/>` +
  `<ellipse class="fur" cx="6" cy="-9.6" rx="2.9" ry="1.9"/>` +
  `<circle class="fur" cx="8.6" cy="-10.6" r="1.6"/>` +
  `<circle class="ear" cx="7.9" cy="-12.1" r=".85"/>` +
  `<circle class="ear" cx="10.1" cy="-10.4" r=".45"/>` +
  `<circle class="eye" cx="8.9" cy="-11" r=".38"/>` +
  `<path class="hat" d="M7.2,-11.7 L10.4,-11.7 L9.6,-13.4 Q9.6,-15.4 11.4,-15.8 Q10,-14.6 9.9,-13 Z"/>` +
  `<path class="hatbrim" d="M6.4,-11.6 L11.2,-11.6"/>` +
  `</g></g>`;

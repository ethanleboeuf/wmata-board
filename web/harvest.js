// Thanksgiving dress-up for the shared map, switched on by `[map] theme =
// "thanksgiving"` in config.toml: a brown-and-gold harvest basemap, a harvest
// moon, turkeys and walking cornucopias crossing under the lanes, leaves
// drifting down, a pumpkin pie beside home, autumn leaves on the hospital, and
// the rider as a little pilgrim (her rat too). Built like spooky.js; map.js
// picks one theme object by name.

export const HARVEST_LAND = "#1a120c";

const PAINT = {
  background: { "background-color": HARVEST_LAND },
  earth: { "fill-color": HARVEST_LAND },
  landuse: { "fill-color": "#26150f" },
  water: { "fill-color": "#0f2426" },
  buildings: { "fill-color": "#26150f" },
  "roads-minor": { "line-color": "#3a2718" },
  "roads-major": { "line-color": "#c98a2a", "line-opacity": 0.4 },
};

// Retint the Board-navy style (web/style.json) and give the major roads a
// soft gold glow underneath, the same way spookyStyle does.
export function harvestStyle(style) {
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
  return { ...style, name: "Board thanksgiving", layers };
}

const f = n => n.toFixed(1);

// ---- walkers (an HTML layer under the SVG overlay) -------------------------
// A turkey strutting right: a fanned tail in three rings, a bobbing head, and
// legs that step. The arms only show on the one doing the griddy (board.css):
// shoulder at 28,29, each a hinged upper arm and forearm ending in a ring of a
// hand: the near one goes over its eye, the far one past its beak, like goggles.
const ARM = cls => `<g class="arm ${cls}" transform="translate(28,29)"><g class="upper"><path d="M0,0 V11"/>` +
  `<g transform="translate(0,11)"><g class="fore"><path d="M0,0 V9.6"/><circle cy="12.4" r="2.8"/></g></g></g></g>`;
const fan = (ry, fill) => [-72, -48, -24, 0, 24, 48, 72].map(a =>
  `<ellipse cx="18" cy="${f(29 - ry)}" rx="4.6" ry="${ry}" fill="${fill}" ` +
  `transform="rotate(${a} 18 29)"/>`).join("");
const TURKEY = `<svg viewBox="-18 -8 74 62" width="74" height="62">` +   // room for the full fan
  `<g class="tail">${fan(17, "#b5452a")}${fan(13, "#e0a23a")}${fan(9, "#7a4a26")}</g>` +
  `<path class="leg step" d="M21,39 L20,50 M17.6,50 L22.4,50"/>` +
  `<path class="leg step2" d="M27,39 L28,50 M25.6,50 L30.4,50"/>` +
  ARM("far") +
  `<ellipse class="tbody" cx="24" cy="32" rx="11.5" ry="9.5"/>` +
  `<path class="twing" d="M15,30 Q22,25 28,31 Q23,38 15,30 Z"/>` +
  `<g class="head"><path class="neck" d="M30,30 Q35,26 35.5,18"/>` +
  `<circle class="thead" cx="36" cy="16.5" r="4.6"/>` +
  `<path class="beak" d="M40,15.2 L44.2,16.8 L40,18.4 Z"/>` +
  `<path class="wattle" d="M39.6,18 Q41,22 38.6,24.4 Q37.4,21 38.4,18 Z"/>` +
  `<circle cx="37.4" cy="15" r="1.3" fill="#fff"/><circle cx="37.8" cy="15" r=".7" fill="#111"/></g>` +
  ARM("near") + `</svg>`;
// A cornucopia waddling left: a woven horn curling up at the tip, spilling a
// pumpkin, an apple and grapes from its mouth, with eyes and stomping legs.
const CORNUCOPIA = `<svg viewBox="0 0 64 50" width="64" height="50">` +
  `<path class="leg step" d="M29,32 L28,46 M25.4,46 L30.2,46"/>` +
  `<path class="leg step2" d="M41,28 L42,46 M39.6,46 L44.4,46"/>` +
  `<path class="horn" d="M18,9 Q38,10 50,9 Q58,8 58.6,3 Q58.4,-.4 55,2 Q56.4,6 51.5,14 Q43,30 18,35 Z"/>` +
  `<path class="weave" d="M26,9.6 Q30,22 26,33.6 M34,10 Q37.6,21 34,31 M42,10 Q45,18.5 42,26.2 M49.4,9.4 Q51.4,13 49.6,17"/>` +
  `<ellipse class="mouth" cx="18" cy="22" rx="5.2" ry="13"/>` +
  `<circle cx="13.5" cy="12" r="2.6" fill="#7b4fb0"/><circle cx="17" cy="11" r="2.6" fill="#6b3fa0"/>` +
  `<circle cx="15.4" cy="15" r="2.6" fill="#8a5cc2"/>` +
  `<circle cx="9" cy="20" r="4.8" fill="#c8322b"/><path d="M9,15.4 L9.8,13.4" stroke="#5a3616" stroke-width="1.1"/>` +
  `<ellipse cx="11" cy="30" rx="8" ry="5.8" fill="#e8771e"/>` +
  `<path d="M8,24.6 Q6.8,30 8,35.4 M14,24.6 Q15.2,30 14,35.4" fill="none" stroke="#c45f12" stroke-width="1"/>` +
  `<path d="M11,24.4 L12,21.6" stroke="#4f8a2e" stroke-width="1.8" stroke-linecap="round"/>` +
  `<path d="M20.5,28 Q26,25 25,32 Q21,32 20.5,28 Z" fill="#5f9a3a"/>` +
  `<circle cx="38" cy="18" r="2.2" fill="#fff"/><circle cx="37.3" cy="18.2" r="1.1" fill="#111"/>` +
  `<g class="wink"><circle cx="44" cy="16.6" r="2" fill="#fff"/><circle cx="43.3" cy="16.8" r="1" fill="#111"/></g></svg>`;
// [kind, top %, seconds to cross, delay s]; negative delays start them mid-walk.
// The "turkey griddy" one heel-taps across swinging its arms, then holds its hands
// up over its eyes like glasses, Justin Jefferson style.
const WALKERS = [
  ["turkey", 22, 90, -15], ["turkey griddy", 56, 110, -70], ["turkey", 82, 100, -40],
  ["cornucopia", 12, 120, -30], ["cornucopia", 40, 105, -85], ["cornucopia", 70, 130, -5],
];
const MOON = `<svg class="moon" viewBox="0 0 96 96" width="96" height="96">` +
  `<defs><radialGradient id="harvestglow"><stop offset=".45" stop-color="#ffb84d" stop-opacity=".5"/>` +
  `<stop offset="1" stop-color="#ffb84d" stop-opacity="0"/></radialGradient></defs>` +
  `<circle cx="48" cy="48" r="48" fill="url(#harvestglow)"/><circle cx="48" cy="48" r="26" fill="#f2a541"/>` +
  `<circle cx="40" cy="42" r="5.5" fill="#dc8a2e"/><circle cx="57" cy="56" r="4" fill="#dc8a2e"/>` +
  `<circle cx="55" cy="37" r="2.4" fill="#dc8a2e"/><circle cx="38" cy="58" r="2" fill="#dc8a2e"/></svg>`;

// A maple leaf centered on 0,0, about 18 wide.
const LEAF = "M0,-9 L2,-4.4 L5.2,-6.2 L4.2,-1.2 L8.4,-1.4 L5.4,2 L6.4,4.4 L1,3.2 L.9,8.6 L-.9,8.6 " +
             "L-1,3.2 L-6.4,4.4 L-5.4,2 L-8.4,-1.4 L-4.2,-1.2 L-5.2,-6.2 L-2,-4.4 Z";
const LEAF_COLORS = ["#c8322b", "#e0a23a", "#d0601e", "#b5452a", "#e8b84a"];
// [left %, seconds to fall, delay s, sideways drift px]
const FALLING = [[8, 26, -3, 60], [24, 31, -17, -40], [41, 23, -9, 50], [57, 29, -22, -60],
                 [72, 25, -12, 45], [88, 33, -27, -50], [33, 35, -30, 30]];

// The Lucy-and-the-football gag, every few minutes in the lower left: a
// cornucopia holds a football for a turkey, yanks it away at the last second,
// and the turkey flips onto its back. Choreographed in board.css (gag-*).
const GAG_FIRST_MS = 15000, GAG_EVERY_MS = 180000;
const FOOTBALL = `<svg class="holder" viewBox="0 0 34 26" width="34" height="26">` +
  `<g transform="rotate(-15 8 15)"><ellipse cx="8" cy="15" rx="5.5" ry="10" fill="#8a4a22" stroke="#4a2810" stroke-width="1"/>` +
  `<path d="M8,10 V20 M6.4,12 H9.6 M6.4,14.6 H9.6 M6.4,17.2 H9.6" stroke="#fbf6ea" stroke-width=".9" fill="none"/></g>` +
  `<path d="M33,7 Q22,2 10,4.6" fill="none" stroke="#c98a3e" stroke-width="2.2" stroke-linecap="round"/>` +
  `<circle cx="9.6" cy="4.8" r="2.3" fill="#c98a3e"/></svg>`;
const PUFF = `<svg viewBox="-3 -7 6 14" width="6" height="14"><path d="M0,-7 Q3,0 0,7 Q-3,0 0,-7 Z" fill="#b5452a"/></svg>`;
const GAG = `<div class="gag">` +
  `<div class="gag-corn"><div class="sprite">${CORNUCOPIA}</div>${FOOTBALL}</div>` +
  `<div class="gag-turkey">${TURKEY}</div>` +
  `<div class="gag-puff p1">${PUFF}</div><div class="gag-puff p2">${PUFF}</div><div class="gag-puff p3">${PUFF}</div>` +
  `<div class="gag-bubble">AAUGH!</div></div>`;

export function harvestLayer() {
  const div = document.createElement("div");
  div.className = "harvest";
  div.innerHTML = MOON +
    FALLING.map(([left, secs, delay, drift], i) =>
      `<div class="fall" style="left:${left}%;animation-duration:${secs}s;animation-delay:${delay}s">` +
      `<div class="sway" style="--drift:${drift}px;animation-delay:${delay / 2}s">` +
      `<svg viewBox="-10 -10 20 20" width="18" height="18"><path d="${LEAF}" fill="${LEAF_COLORS[i % LEAF_COLORS.length]}"/></svg>` +
      `</div></div>`).join("") +
    WALKERS.map(([kind, top, secs, delay]) =>
      `<div class="walk ${kind}" style="top:${top}%;animation-duration:${secs}s;animation-delay:${delay}s">` +
      `<div class="sprite">${kind.startsWith("turkey") ? TURKEY : CORNUCOPIA}</div></div>`).join("") +
    GAG;
  const gag = div.querySelector(".gag");
  const walking = on => gag.classList.toggle("walking", on);   // the cornucopia walks in and out, not while holding
  const play = () => {
    gag.classList.remove("play"); void gag.offsetWidth; gag.classList.add("play");
    walking(true);
    setTimeout(() => walking(false), 1600);
    setTimeout(() => walking(true), 7400);
  };
  setTimeout(play, GAG_FIRST_MS);
  setInterval(play, GAG_EVERY_MS);
  return div;
}

// ---- harvest stations (SVG strings, drawn by map.js's drawStatic) -----------
export const PIE_GLOW = `<radialGradient id="pieglow"><stop offset="0" stop-color="#ffb84d" stop-opacity=".55"/>` +
  `<stop offset="1" stop-color="#ffb84d" stop-opacity="0"/></radialGradient>`;

// A pumpkin pie with crimped crust, a dollop of whipped cream and steam.
export function pumpkinPie(x, y) {
  return `<g class="pie" transform="translate(${f(x)},${f(y)}) scale(1.2)">` +
    `<circle r="26" fill="url(#pieglow)"/>` +
    `<path d="M-15,0 V4 A15,6 0 0 0 15,4 V0 Z" fill="#b8692c" stroke="${HARVEST_LAND}" stroke-width="2"/>` +
    `<ellipse rx="15" ry="6" fill="#e8a24a" stroke="${HARVEST_LAND}" stroke-width="2"/>` +
    `<ellipse rx="13.4" ry="5.1" fill="none" stroke="#f6cf8a" stroke-width="1.5" stroke-dasharray="2 1.5"/>` +
    `<ellipse rx="11.4" ry="4.1" fill="#c8611e"/>` +
    `<path d="M-5,-.6 Q-5.6,-4.6 -1.8,-4.8 Q-1,-8.6 1.8,-7 Q4.8,-6 4.4,-3 Q5.8,-1.2 3.4,.2 Q0,1.2 -3.4,.2 Q-5.4,.2 -5,-.6 Z" ` +
    `fill="#fff8ec" stroke="#e6d6bb" stroke-width=".6"/>` +
    `<path class="steam" d="M-6,-10 q-2,-3 0,-6 q2,-3 0,-6"/>` +
    `<path class="steam s2" d="M0,-12 q-2,-3 0,-6 q2,-3 0,-6"/>` +
    `<path class="steam s3" d="M6,-10 q-2,-3 0,-6 q2,-3 0,-6"/></g>`;
}

// A few autumn leaves tucked over the top-left corner of the hospital tile.
export function fallLeaves(x, y) {
  const leaf = (dx, dy, rot, s, fill) =>
    `<path d="${LEAF}" fill="${fill}" stroke="${HARVEST_LAND}" stroke-width="1.2" ` +
    `transform="translate(${f(x + dx)},${f(y + dy)}) rotate(${rot}) scale(${s})"/>`;
  return leaf(-14, -6, -70, 0.8, "#e0a23a") + leaf(-6, -15, 25, 0.75, "#c8322b") + leaf(-12, -13, -20, 0.95, "#d0601e");
}

// ---- the rider, dressed as a pilgrim -----------------------------------------
// Same pose and rat as map.js's RIDER: a brown dress with a wide white collar
// and a tall buckled hat; the rat gets a buckled hat of its own.
export const PILGRIM = `<g transform="scale(2.4) translate(-1.2,4.2)"><g class="bob">` +
  `<path class="hair" d="M-5.4,-26 C-5.6,-20 -6.4,-17.5 -4.2,-16.4 L4.2,-16.4 C6.4,-17.5 5.6,-20 5.4,-26 A5.4,5.6 0 0 0 -5.4,-26 Z"/>` +
  `<path class="skin" d="M-2.6,-12 L-3.2,-8.6 M2.6,-12 L3.2,-8.6 M-2,-18.6 L-6.2,-14.4"/>` +
  `<path class="wave skin" d="M2,-18.6 L6.6,-23.4"/>` +
  `<path class="coat" d="M0,-19.6 L-5,-11.2 L5,-11.2 Z"/>` +
  `<path class="collar" d="M-3.8,-20 L3.8,-20 L2.4,-17 L0,-18.2 L-2.4,-17 Z"/>` +
  `<circle class="face" cx="0" cy="-24.6" r="3.6"/>` +
  `<circle class="eye" cx="-1.3" cy="-24.4" r=".42"/><circle class="eye" cx="1.3" cy="-24.4" r=".42"/>` +
  `<path class="smile" d="M-1,-22.7 Q0,-21.9 1,-22.7"/>` +
  `<path class="phat" d="M-3.7,-27.2 L-3.1,-33.6 L3.1,-33.6 L3.7,-27.2 Z"/>` +
  `<path class="pband" d="M-3.6,-28.2 L3.6,-28.2 L3.5,-29.8 L-3.5,-29.8 Z"/>` +
  `<rect class="buckle" x="-1.2" y="-30.1" width="2.4" height="2.2"/>` +
  `<ellipse class="phat" cx="0" cy="-27.1" rx="7" ry="1.4"/>` +
  `</g><g class="rat" transform="translate(-0.4,1) translate(6,-8) scale(1.5) translate(-6,8)">` +
  `<path class="tail" d="M3.6,-9.4 Q1.6,-7.6 3.2,-6.2 Q4.6,-5.2 3.6,-4"/>` +
  `<ellipse class="fur" cx="6" cy="-9.6" rx="2.9" ry="1.9"/>` +
  `<circle class="fur" cx="8.6" cy="-10.6" r="1.6"/>` +
  `<circle class="ear" cx="7.9" cy="-12.1" r=".85"/>` +
  `<circle class="ear" cx="10.1" cy="-10.4" r=".45"/>` +
  `<circle class="eye" cx="8.9" cy="-11" r=".38"/>` +
  `<path class="phat" d="M7.6,-11.7 L10.4,-11.7 L10,-14.6 L8,-14.6 Z"/>` +
  `<rect class="buckle" x="8.5" y="-12.9" width="1" height="1"/>` +
  `<path class="pbrim" d="M6.6,-11.6 L11.4,-11.6"/>` +
  `</g></g>`;

export const THANKSGIVING = { land: HARVEST_LAND, style: harvestStyle, layer: harvestLayer, defs: PIE_GLOW,
                              besideHome: pumpkinPie, onLandmark: fallLeaves, rider: PILGRIM };

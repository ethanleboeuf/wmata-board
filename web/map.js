// Shared map: MapLibre draws only the Board-navy basemap; an SVG overlay on
// top draws lanes, stations, labels, landmarks and gliding trains, re-projected
// with map.project() on every move so the wall and the phone share this file.
// The overlay never takes pointer events (pans and pinches reach the map);
// the phone hit-tests taps against the drawn trains with trainAt(). The trip
// /api/positions names as `ride` gets a little rider on top (the easter egg).
// While she rides, someone by home waves her off (mornings) or dances her
// home in confetti (afternoons) (wave.js).
// A config theme (`net.theme`) can dress all of it up; see spooky.js.
import { LINE_COLORS, LINE_LETTER, escapeHtml, liveLabel } from "./format.js";
import { buildTrack, snapToTrack, pointAt, laneOffset, headingSign, coverView,
         mercator, unmercator, Glider } from "./track.js";
import { SPOOKY_LAND, spookyStyle, spookLayer, jackOLantern, cobweb, WITCH } from "./spooky.js";
import { waveMode, waveHtml, cheerHtml } from "./wave.js";

const NS = "http://www.w3.org/2000/svg";
const LW = 7;
const LANE = { RD: 0, OR: -0.5, SV: 0.5, BL: 1.5, GR: -0.5, YL: 0.5 };
const ORDER = ["RD", "GR", "YL", "BL", "OR", "SV"];
const DARK_TEXT = new Set(["OR", "SV", "YL"]);
const LAND = "#0f151d";
const POSITIONS_MS = 5000;
const POSITIONS_STALE_MS = 120000;   // no good /api/positions for this long -> fade trains
const FETCH_TIMEOUT_MS = 8000;       // a hung request must never stall a poll loop
// Hand-tuned label placement from the approved prototype: [dx, dy, anchor, name].
const LABEL_HINTS = {
  K04: [0, 30, "middle", "Ballston"], K02: [0, 30, "middle"], C05: [16, -12, "start"],
  C04: [0, -18, "middle", "Foggy Bottom"], C01: [-16, 28, "end", "Metro Center"],
  D03: [16, 28, "start", "L'Enfant Plaza"], B03: [0, 30, "middle", "Union Station"],
  A03: [-16, -4, "end", "Dupont Circle"], C07: [16, 6, "start", "Pentagon"],
  F05: [14, 22, "start", "Navy Yard"], B05: [-16, 5, "end", "Brookland"],
};

// A little blonde woman in a pink dress and a conductor's cap sitting on the
// badge, one arm waving, with her pet rat beside her (styled in board.css).
const RIDER = `<g transform="scale(2.4) translate(-1.2,4.2)"><g class="bob">` +
  `<path class="hair" d="M-5.4,-26 C-5.6,-20 -6.4,-17.5 -4.2,-16.4 L4.2,-16.4 C6.4,-17.5 5.6,-20 5.4,-26 A5.4,5.6 0 0 0 -5.4,-26 Z"/>` +
  `<path class="skin" d="M-2.6,-12 L-3.2,-8.6 M2.6,-12 L3.2,-8.6 M-2,-18.6 L-6.2,-14.4"/>` +
  `<path class="wave skin" d="M2,-18.6 L6.6,-23.4"/>` +
  `<path class="dress" d="M0,-19.6 L-5,-11.2 L5,-11.2 Z"/>` +
  `<circle class="face" cx="0" cy="-24.6" r="3.6"/>` +
  `<circle class="eye" cx="-1.3" cy="-24.4" r=".42"/><circle class="eye" cx="1.3" cy="-24.4" r=".42"/>` +
  `<path class="smile" d="M-1,-22.7 Q0,-21.9 1,-22.7"/>` +
  `<path class="cap" d="M-3.9,-26.5 L-4.6,-29.4 Q0,-30.6 4.6,-29.4 L3.9,-26.5 Z"/>` +
  `<path class="band" d="M-3.95,-27.6 L3.95,-27.6"/>` +
  `<path class="cap" d="M-4.3,-26.6 L3.6,-26.6 Q6,-26.5 6.6,-25.4 L-4.3,-25.6 Z"/>` +
  `<circle class="badge" cx="0" cy="-28.7" r=".6"/>` +
  `</g><g class="rat" transform="translate(-0.4,1) translate(6,-8) scale(1.5) translate(-6,8)">` +
  `<path class="tail" d="M3.6,-9.4 Q1.6,-7.6 3.2,-6.2 Q4.6,-5.2 3.6,-4"/>` +
  `<ellipse class="fur" cx="6" cy="-9.6" rx="2.9" ry="1.9"/>` +
  `<circle class="fur" cx="8.6" cy="-10.6" r="1.6"/>` +
  `<circle class="ear" cx="7.9" cy="-12.1" r=".85"/>` +
  `<circle class="ear" cx="10.1" cy="-10.4" r=".45"/>` +
  `<circle class="eye" cx="8.9" cy="-11" r=".38"/>` +
  `</g></g>`;

const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};

async function getJson(url) {
  for (let delay = 1000; ; delay = Math.min(delay * 2, 30000)) {
    try {
      const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
      if (r.ok) return await r.json();
    } catch (err) { /* retry */ }
    await new Promise(res => setTimeout(res, delay));
  }
}

async function loadStyle() {
  const style = await getJson("/static/style.json");
  let haveBasemap = false;
  try { haveBasemap = (await fetch("/basemap.pmtiles", { method: "HEAD", signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) })).ok; } catch (err) { /* offline */ }
  if (haveBasemap) {
    style.sources.protomaps.url = `pmtiles://${location.origin}/basemap.pmtiles`;
  } else {
    // Review focus 5: no basemap yet -> keep the land-colored background only.
    console.warn("basemap.pmtiles missing; drawing the overlay on plain land");
    delete style.sources.protomaps;
    style.layers = style.layers.filter(l => l.type === "background");
  }
  return style;
}

function badge(line) {
  const c = (LINE_COLORS[line] || ["#888"])[0];
  return `<circle r="16" fill="url(#glow-${line})"/>` +
    `<circle r="10.5" fill="${c}" stroke="#fff" stroke-width="2"/>` +
    `<text y="4.6" text-anchor="middle" font-family="Inter, sans-serif" font-weight="800" font-size="13" ` +
    `fill="${DARK_TEXT.has(line) ? "#111" : "#fff"}">${LINE_LETTER[line] || "?"}</text>` +
    `<path class="dir" d="M15,-4 L21,0 L15,4 Z" fill="#fff"/>`;
}

export async function createMap(el, { interactive = false, fit = "cover", padding = null } = {}) {
  const [net, baseStyle] = await Promise.all([getJson("/api/network"), loadStyle()]);
  const spooky = net.theme === "halloween";
  const style = spooky ? spookyStyle(baseStyle) : baseStyle;
  const land = spooky ? SPOOKY_LAND : LAND;
  el.classList.toggle("halloween", spooky);
  if (!window.__pmtilesProtocol) {
    window.__pmtilesProtocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", window.__pmtilesProtocol.tile);
  }
  const [w, s, e, n] = net.view.bbox;
  // padding: object or () => {top,bottom,left,right}; only used for non-"cover" fits.
  const pad = () => (typeof padding === "function" ? padding() : padding) || 0;
  const start = fit === "cover" ? coverView(net.view.bbox, el.clientWidth, el.clientHeight) : null;
  const map = new maplibregl.Map({
    container: el, style, interactive, attributionControl: false, fadeDuration: 0,
    ...(start ? { center: start.center, zoom: start.zoom } : { bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: pad() } }),
    dragRotate: false, pitchWithRotate: false, touchPitch: false,
  });
  map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");
  if (interactive) map.touchZoomRotate.disableRotation();

  const tracks = Object.fromEntries(Object.entries(net.lines).map(([k, v]) => [k, buildTrack(v)]));
  const home = net.stations.find(st => st.codes.includes(net.home));

  // ---- SVG overlay ----
  const svg = svgEl("svg", { class: "overlay" });
  svg.innerHTML = `<defs>${ORDER.map(l => `<radialGradient id="glow-${l}">` +
    `<stop offset="0" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0.7"/>` +
    `<stop offset="0.45" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0.28"/>` +
    `<stop offset="1" stop-color="${LINE_COLORS[l][0]}" stop-opacity="0"/></radialGradient>`).join("")}` +
    `<radialGradient id="hosp"><stop offset="0" stop-color="#ff8a9b" stop-opacity=".55"/>` +
    `<stop offset="1" stop-color="#ff8a9b" stop-opacity="0"/></radialGradient>` +
    `<radialGradient id="pumpglow"><stop offset="0" stop-color="#ff8a2a" stop-opacity=".6"/>` +
    `<stop offset="1" stop-color="#ff8a2a" stop-opacity="0"/></radialGradient></defs>` +
    `<g class="static"></g><g class="trains"></g>` +
    `<text class="live" x="24" y="44"><tspan class="dot" fill="#3ddc84">●</tspan> <tspan class="lbl"></tspan></text>`;
  el.appendChild(svg);
  if (spooky) el.insertBefore(spookLayer(), svg);   // ghosts drift under the lanes and trains
  const pulse = document.createElement("div");
  pulse.className = "pulse";
  el.appendChild(pulse);
  const gStatic = svg.querySelector(".static"), gTrains = svg.querySelector(".trains");
  const dotEl = svg.querySelector(".dot"), lblEl = svg.querySelector(".lbl");
  let shownLabel = "";
  function setLabel(count) {
    const text = liveLabel({ stale, count });
    if (text === shownLabel) return;
    shownLabel = text;
    lblEl.textContent = text;
    dotEl.setAttribute("fill", stale ? "#ffb020" : "#3ddc84");
  }

  const project = (lon, lat) => { const p = map.project([lon, lat]); return [p.x, p.y]; };
  const pl = pts => pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");

  function drawStatic() {
    const W = el.clientWidth, H = el.clientHeight, out = [];
    for (const p of net.places) {
      const [x, y] = project(p.lon, p.lat);
      out.push(`<text class="place" x="${x.toFixed(0)}" y="${y.toFixed(0)}" text-anchor="middle">${escapeHtml(p.name)}</text>`);
    }
    const lanes = ORDER.filter(l => net.lines[l]).map(l =>
      [l, laneOffset(net.lines[l].map(([lon, lat]) => project(lon, lat)), LANE[l] * LW)]);
    out.push(`<g fill="none" stroke-linecap="round" stroke-linejoin="round">`);
    for (const [, pts] of lanes) out.push(`<polyline points="${pl(pts)}" stroke="#0a0e14" stroke-width="${LW + 5}"/>`);
    for (const [l, pts] of lanes) out.push(`<polyline points="${pl(pts)}" stroke="${LINE_COLORS[l][0]}" stroke-width="${LW}"/>`);
    out.push(`</g>`);
    for (const st of net.stations) {
      if (st === home) continue;
      const [x, y] = project(st.lon, st.lat);
      if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${st.transfer ? 6.2 : 3.8}" fill="${land}" ` +
               `stroke="#cfd8e3" stroke-width="${st.transfer ? 2.6 : 2}"/>`);
    }
    out.push(`<g class="labels">`);
    for (const code of net.labels) {
      const st = net.stations.find(x => x.codes.includes(code));
      if (!st) continue;
      const [dx, dy, anchor, name] = LABEL_HINTS[code] || [0, 26, "middle"];
      const [x, y] = project(st.lon, st.lat);
      out.push(`<text x="${(x + dx).toFixed(1)}" y="${(y + dy).toFixed(1)}" text-anchor="${anchor}">${escapeHtml((name || st.name).toUpperCase())}</text>`);
    }
    out.push(`</g>`);
    for (const lm of net.landmarks) {
      const [x, y] = project(lm.lon, lm.lat);
      const [first, ...rest] = lm.name.toUpperCase().split(" ");
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="26" fill="url(#hosp)"/>` +
        `<rect x="${(x - 11).toFixed(1)}" y="${(y - 11).toFixed(1)}" width="22" height="22" rx="6" fill="#ff8a9b" stroke="${land}" stroke-width="2.5"/>` +
        `<path d="M${x.toFixed(1)},${(y - 6).toFixed(1)} V${(y + 6).toFixed(1)} M${(x - 6).toFixed(1)},${y.toFixed(1)} H${(x + 6).toFixed(1)}" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/>` +
        (spooky ? cobweb(x, y) : "") +
        `<g class="landmark"><text x="${x.toFixed(1)}" y="${(y + 31).toFixed(1)}">${escapeHtml(first)}</text>` +
        (rest.length ? `<text x="${x.toFixed(1)}" y="${(y + 47).toFixed(1)}">${escapeHtml(rest.join(" "))}</text>` : "") + `</g>`);
    }
    if (home) {
      const [x, y] = project(home.lon, home.lat);
      out.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="10" fill="${land}" stroke="#fff" stroke-width="3.5"/>` +
        `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="#fff"/>` +
        (spooky ? jackOLantern(x + 10, y - 36) : "") +   // beside home: trains stopped there would hide it
        `<text class="home" x="${(x - 18).toFixed(1)}" y="${(y - 22).toFixed(1)}" text-anchor="end">${escapeHtml(home.name.toUpperCase())}</text>`);
      pulse.style.left = `${x}px`;
      pulse.style.top = `${y}px`;
    }
    if (waving) {
      const [x, y] = project(net.wave.lon, net.wave.lat);
      out.push(waving === "cheer" ? cheerHtml(x, y, net.wave.cheer) : waveHtml(x, y, net.wave.message));
    }
    gStatic.innerHTML = out.join("");
  }

  // ---- trains ----
  const glider = new Glider();
  const els = new Map();
  const info = new Map();   // vehicle id -> {line, cars, trip_id} from the last snapshot
  let stale = true, riding = null, waving = null;   // waving: wave.js waveMode
  let lastGoodMs = performance.now();

  function setStale(v) {
    stale = v;
    gTrains.classList.toggle("faded", stale);
  }

  async function pollPositions() {
    let ok = false;
    try {
      const r = await fetch("/api/positions", { cache: "no-store", signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
      if (r.ok) {
        const body = await r.json();
        ok = true;
        lastGoodMs = performance.now();
        setStale(body.stale);
        riding = body.ride ?? null;
        const wave = net.wave ? waveMode(riding) : null;
        if (wave !== waving) { waving = wave; scheduleDraw(); }
        if (body.feed_timestamp !== null) {
          const vs = [];
          info.clear();
          for (const v of body.vehicles) {
            info.set(v.id, { line: v.line, cars: v.cars, trip_id: v.trip_id ?? null });
            const track = tracks[v.line];
            if (!track) continue;
            const { s } = snapToTrack(track, mercator(v.lon, v.lat));
            vs.push({ id: v.id, line: v.line, s, dir: headingSign(track, s, v.heading) });
          }
          glider.update(vs, body.feed_timestamp, performance.now());
        }
      }
    } catch (err) {
      /* keep gliding what we have; fades once failures outlast POSITIONS_STALE_MS */
    } finally {
      if (!ok && performance.now() - lastGoodMs > POSITIONS_STALE_MS) setStale(true);
      setTimeout(pollPositions, POSITIONS_MS);
    }
  }

  function screenAt(line, s) {
    const track = tracks[line];
    const p = pointAt(track, s), q = pointAt(track, s + 1e-7);
    const [x, y] = project(...unmercator(p.x, p.y));
    let [x2, y2] = project(...unmercator(q.x, q.y));
    if (Math.hypot(x2 - x, y2 - y) < 1e-6) { x2 = x + p.dx; y2 = y + p.dy; }
    const dx = x2 - x, dy = y2 - y, l = Math.hypot(dx, dy) || 1;
    const off = LANE[line] * LW;
    return [x - dy / l * off, y + dx / l * off, Math.atan2(dy, dx)];
  }

  let lastFrame = 0;
  function frame(now) {
    requestAnimationFrame(frame);
    if (now - lastFrame < 33) return;           // ~30 fps is plenty, and kind to the Pi
    lastFrame = now;
    const W = el.clientWidth, H = el.clientHeight, seen = new Set();
    let visible = 0;
    for (const v of glider.at(now)) {
      let e = els.get(v.id);
      if (!e || e.line !== v.line) {
        e?.g.remove();
        const g = svgEl("g");
        g.innerHTML = badge(v.line);
        gTrains.appendChild(g);
        e = { g, dir: g.querySelector(".dir"), line: v.line };
        els.set(v.id, e);
      }
      const [x, y, ang] = screenAt(v.line, v.s);
      const deg = ang * 180 / Math.PI + (v.dir < 0 ? 180 : 0);
      e.g.setAttribute("transform", `translate(${x.toFixed(1)},${y.toFixed(1)})`);
      e.dir.setAttribute("transform", `rotate(${deg.toFixed(0)})`);
      e.g.style.opacity = v.opacity.toFixed(2);
      e.x = x; e.y = y; e.opacity = v.opacity;
      const on = riding !== null && info.get(v.id)?.trip_id === riding;
      if (on && !e.rider) {
        e.rider = svgEl("g", { class: "rider" });
        e.rider.innerHTML = spooky ? WITCH : RIDER;
        e.g.appendChild(e.rider);
      } else if (!on && e.rider) { e.rider.remove(); e.rider = null; }
      if (on && gTrains.lastChild !== e.g) gTrains.appendChild(e.g);   // she rides on top
      if (x > 0 && y > 0 && x < W && y < H && v.opacity > 0.5) visible++;
      seen.add(v.id);
    }
    for (const [id, e] of els) if (!seen.has(id)) { e.g.remove(); els.delete(id); }
    setLabel(visible);
  }

  function refit() {
    if (fit !== "cover") return;
    const v = coverView(net.view.bbox, el.clientWidth, el.clientHeight);
    map.jumpTo({ center: v.center, zoom: v.zoom });
  }
  // Rebuilding the static SVG is the expensive part; coalesce move/load/resize
  // bursts (the phone pans interactively) into at most one redraw per frame.
  let drawPending = false;
  function scheduleDraw() {
    if (drawPending) return;
    drawPending = true;
    requestAnimationFrame(() => { drawPending = false; drawStatic(); });
  }
  const ro = new ResizeObserver(() => { map.resize(); refit(); scheduleDraw(); });
  ro.observe(el);
  map.on("move", scheduleDraw);
  map.on("load", scheduleDraw);
  drawStatic();
  pollPositions();
  requestAnimationFrame(frame);

  return {
    map,
    recenter() {
      if (fit === "cover") refit();
      else map.fitBounds([[w, s], [e, n]], { duration: 600, padding: pad() });
    },
    destroy() { ro.disconnect(); map.remove(); },
    // The drawn train nearest a screen point (map container px), within `radius`.
    trainAt(x, y, radius = 24) {
      let best = null, bestD = radius;
      for (const [id, e] of els) {
        const d = Math.hypot(e.x - x, e.y - y);
        if (e.opacity > 0.5 && d <= bestD) { best = id; bestD = d; }
      }
      return best === null ? null : { id: best, line: els.get(best).line, ...info.get(best) };
    },
  };
}

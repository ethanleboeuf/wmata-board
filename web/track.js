// Track geometry and train gliding. Pure (no DOM, no MapLibre) so node can
// test it. Positions along a line are arc lengths `s` in Web Mercator world
// units (0..1), which don't change with zoom -- the phone can pan and pinch
// mid-glide and nothing jumps.

export const TILE = 512;

export function mercator(lon, lat) {
  const sin = Math.sin(lat * Math.PI / 180);
  return [(lon + 180) / 360, 0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)];
}

export function unmercator(x, y) {
  return [x * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI];
}

export function kmToMerc(km, lat = 38.9) {
  return km / (40075.017 * Math.cos(lat * Math.PI / 180));
}
export const JUMP_MERC = kmToMerc(1);

// Center + zoom at which the bbox COVERS a width x height panel.
export function coverView([w, s, e, n], width, height, tileSize = TILE) {
  const [x0, y0] = mercator(w, n), [x1, y1] = mercator(e, s);
  const scale = Math.max(width / (x1 - x0), height / (y1 - y0));
  return { center: unmercator((x0 + x1) / 2, (y0 + y1) / 2), zoom: Math.log2(scale / tileSize) };
}

export function buildTrack(lonlats) {
  const pts = lonlats.map(([lon, lat]) => mercator(lon, lat));
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  }
  return { pts, cum, length: cum[cum.length - 1] };
}

export function snapToTrack(track, [px, py]) {
  const { pts, cum } = track;
  let best = 0, bestD = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1];
    const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-30;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
    const qx = ax + t * dx, qy = ay + t * dy, d = (qx - px) ** 2 + (qy - py) ** 2;
    if (d < bestD) { bestD = d; best = cum[i] + t * Math.sqrt(l2); }
  }
  return { s: best, dist: Math.sqrt(bestD) };
}

export function pointAt(track, s) {
  const { pts, cum, length } = track;
  s = Math.max(0, Math.min(length, s));
  let lo = 0, hi = pts.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] <= s) lo = m; else hi = m; }
  const [ax, ay] = pts[lo], [bx, by] = pts[hi];
  const seg = (cum[hi] - cum[lo]) || 1e-30, t = (s - cum[lo]) / seg;
  const len = Math.hypot(bx - ax, by - ay) || 1e-30;
  return { x: ax + (bx - ax) * t, y: ay + (by - ay) * t, dx: (bx - ax) / len, dy: (by - ay) / len };
}

// Parallel lanes for shared track, in screen pixels.
export function laneOffset(points, off) {
  if (!off) return points.map(p => [p[0], p[1]]);
  return points.map(([x, y], i) => {
    const a = points[Math.max(i - 1, 0)], b = points[Math.min(i + 1, points.length - 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
    return [x - dy / l * off, y + dx / l * off];
  });
}

// +1 if the bearing points along increasing s, -1 against, 0 if unclear.
export function headingSign(track, s, bearingDeg) {
  if (bearingDeg === null || bearingDeg === undefined) return 0;
  const { dx, dy } = pointAt(track, s);
  const b = bearingDeg * Math.PI / 180;
  const d = dx * Math.sin(b) + dy * -Math.cos(b);    // mercator y points south
  return d > 0.3 ? 1 : d < -0.3 ? -1 : 0;
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Keeps the previous and latest snapshot per vehicle and animates between them
// over the measured interval between snapshots -- ~one interval behind real
// time, but smooth.
export class Glider {
  constructor({ jump = JUMP_MERC, fadeMs = 1500, minMs = 1000, maxMs = 15000 } = {}) {
    Object.assign(this, { jump, fadeMs, minMs, maxMs });
    this.v = new Map();
    this.lastTs = null;
  }

  _s(e, nowMs) {
    if (!e.dur) return e.to;
    return e.from + (e.to - e.from) * clamp((nowMs - e.t0) / e.dur, 0, 1);
  }

  update(vehicles, feedTs, nowMs) {
    if (feedTs === this.lastTs) return;
    const first = this.lastTs === null;
    const backwards = !first && feedTs < this.lastTs;
    const dur = first || backwards ? 0 : clamp((feedTs - this.lastTs) * 1000, this.minMs, this.maxMs);
    this.lastTs = feedTs;
    const seen = new Set();
    for (const nv of vehicles) {
      seen.add(nv.id);
      const old = this.v.get(nv.id);
      const same = old && !old.leaving && old.line === nv.line;
      const cur = same ? this._s(old, nowMs) : nv.s;
      const glide = same && dur > 0 && Math.abs(nv.s - cur) <= this.jump;
      const from = glide ? cur : nv.s;
      const moved = Math.sign(nv.s - (same ? cur : nv.s));
      const dir = nv.dir || moved || (same ? old.dir : 0) || 1;
      this.v.set(nv.id, {
        id: nv.id, line: nv.line, from, to: nv.s, t0: nowMs, dur: glide ? dur : 0, dir,
        born: same ? old.born : (first ? nowMs - this.fadeMs : nowMs), leaving: null,
      });
    }
    for (const e of this.v.values()) {
      if (!seen.has(e.id) && !e.leaving) {
        e.from = e.to = this._s(e, nowMs);
        e.dur = 0;
        e.leaving = nowMs;
      }
    }
  }

  at(nowMs) {
    const out = [];
    for (const [id, e] of this.v) {
      let opacity;
      if (e.leaving !== null) {
        opacity = 1 - (nowMs - e.leaving) / this.fadeMs;
        if (opacity <= 0) { this.v.delete(id); continue; }
      } else {
        opacity = clamp((nowMs - e.born) / this.fadeMs, 0, 1);
      }
      out.push({ id, line: e.line, s: this._s(e, nowMs), dir: e.dir, opacity });
    }
    return out;
  }
}

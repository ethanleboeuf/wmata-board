// The Thanksgiving map's leaves as a snowglobe: they flutter down, pile up on
// the floor (the bottom of the map, or the top of the phone's sheet) up to a
// cap, slide when the phone tilts, and fly back up when it's shaken. Pure
// state and physics only; harvest.js draws it and feeds it the phone's motion.

const BIN = 14;           // px per pile column
const LAYER = 4.5;        // px a resting leaf adds to its column
const SLIP = 2;           // layers a column may stand over a neighbor before a leaf rolls off
const FALL_S = 28;        // seconds to fall the height of the map
const DRAG = 1.6;         // per second; terminal speed is gravity / DRAG
const SPAWN_S = 4;        // a new leaf at the top this often, as the old CSS ones did
const SLIDE = 160;        // px/s a resting leaf slides at full tilt
const FRICTION = 0.12;    // tilt (sin of the angle) the pile holds still under
const FADE_S = 2;

export class LeafGlobe {
  constructor({ max = 90, colors = 5, rand = Math.random } = {}) {
    this.max = max; this.colors = colors; this.rand = rand;
    this.leaves = [];     // everything drawn
    this.pile = [];       // the resting ones, in landing order
    this.gx = 0;          // sideways gravity, -1..1 (sin of the phone's tilt)
    this.w = 0; this.floor = 0; this.spawnIn = 0; this.n = 0;
  }

  // Width and floor in px. The first call scatters a handful already mid-fall.
  resize(w, floor) {
    const first = !this.w;
    this.w = w; this.floor = floor;
    if (first) for (let i = 0; i < 7; i++) this.spawn(this.rand() * floor);
  }

  spawn(y = -12) {
    const r = this.rand;
    this.leaves.push({ x: r() * this.w, y, vx: 0, vy: 0, rot: r() * 6.28, spin: (r() - 0.5) * 2,
                       phase: r() * 6.28, size: 0.8 + r() * 0.3, color: this.n++ % this.colors,
                       alpha: 0.75, resting: false, fading: false, dx: 0, dy: 0, ry: 0 });
  }

  // strength 0..1: every resting leaf is thrown up, the falling ones get knocked about.
  shake(strength) {
    const r = this.rand, up = this.floor * DRAG * strength;
    for (const l of this.leaves) {
      if (l.fading) continue;
      if (l.resting) { l.resting = false; l.x = l.dx; l.y = l.dy; l.vx = 0; l.vy = 0; }
      l.vy -= up * (0.4 + r() * 0.6);
      l.vx += (r() - 0.5) * up;
      l.spin += (r() - 0.5) * 12 * strength;
    }
    this.pile = [];
  }

  step(dt) {
    const g = this.floor / FALL_S * DRAG, gx = Math.max(-0.9, Math.min(0.9, this.gx));
    const gy = Math.sqrt(1 - gx * gx);
    if ((this.spawnIn -= dt) <= 0) { this.spawnIn = SPAWN_S; this.spawn(); }
    const surface = this.layout();
    for (const l of this.leaves) {
      if (l.resting) continue;
      if (l.fading) { l.alpha -= 0.75 * dt / FADE_S; l.dy = this.floor + l.ry; continue; }
      l.phase += dt * 1.6;
      l.vx += (g * gx + Math.sin(l.phase) * g * 0.6 - DRAG * l.vx) * dt;
      l.vy += (g * gy - DRAG * l.vy) * dt;
      l.x += l.vx * dt; l.y += l.vy * dt;
      l.rot += (l.spin + Math.cos(l.phase) * 0.8) * dt;
      l.spin *= Math.exp(-dt);
      if (l.x < 0) { l.x = 0; l.vx = Math.abs(l.vx) * 0.5; }
      if (l.x > this.w) { l.x = this.w; l.vx = -Math.abs(l.vx) * 0.5; }
      l.dx = l.x; l.dy = l.y;
      const top = this.floor - surface[this.bin(l.x)] - LAYER;
      if (l.vy > 0 && l.y >= top) { l.y = top; this.land(l); }
    }
    // The pile slides with the tilt and eases toward where layout() stacked it,
    // measured from the floor so it rides the phone's sheet without lagging.
    const slide = Math.sign(gx) * Math.max(0, Math.abs(gx) - FRICTION) * SLIDE * dt;
    const ease = Math.min(1, dt * 8);
    for (const l of this.pile) {
      l.x = Math.max(0, Math.min(this.w, l.x + slide));
      l.dx += (l.tx - l.dx) * ease; l.ry += (l.ty - this.floor - l.ry) * ease;
      l.dy = this.floor + l.ry;
    }
    this.leaves = this.leaves.filter(l => l.alpha > 0);
  }

  land(l) {
    l.resting = true; l.vx = l.vy = 0; l.dy = l.ty = l.y; l.tx = l.x; l.ry = l.y - this.floor;
    this.pile.push(l);
    if (this.pile.length > this.max) {   // the oldest one fades out where it lies
      const old = this.pile.shift();
      old.resting = false; old.fading = true;
    }
  }

  bin(x) { return Math.max(0, Math.min(this.bins() - 1, Math.floor(x / BIN))); }
  bins() { return Math.max(1, Math.ceil(this.w / BIN)); }

  // Stack the pile column by column in landing order; a leaf landing on a
  // column that stands too far over a neighbor rolls off toward it (downhill
  // with the tilt first). Returns each column's height in px.
  layout() {
    const h = new Array(this.bins()).fill(0), dir = this.gx < 0 ? -1 : 1;
    for (const l of this.pile) {
      let b = this.bin(l.x);
      for (;;) {
        const n = [b + dir, b - dir].find(n => n >= 0 && n < h.length && h[n] + SLIP * LAYER < h[b]);
        if (n === undefined) break;
        b = n;
      }
      if (this.bin(l.x) !== b) l.x = (b + 0.5) * BIN;
      l.tx = l.x; l.ty = this.floor - h[b] - LAYER;
      h[b] += LAYER;
    }
    return h;
  }
}

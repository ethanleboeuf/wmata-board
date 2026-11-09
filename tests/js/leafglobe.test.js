import test from "node:test";
import assert from "node:assert/strict";
import { LeafGlobe } from "../../web/leafglobe.js";

// A seeded random so runs repeat.
const seeded = (s = 1) => () => (s = (s * 16807) % 2147483647) / 2147483647;
const run = (globe, secs, dt = 1 / 30) => { for (let t = 0; t < secs; t += dt) globe.step(dt); };
const fresh = opts => { const g = new LeafGlobe({ rand: seeded(), ...opts }); g.resize(400, 600); return g; };

test("leaves fall and pile up on the floor", () => {
  const g = fresh();
  run(g, 120);
  assert.ok(g.pile.length >= 20, `only ${g.pile.length} landed`);
  for (const l of g.pile) {
    assert.ok(l.dy <= 600 && l.dy > 500, `resting at ${l.dy}`);
    assert.ok(l.dx >= 0 && l.dx <= 400);
  }
});

test("the pile stops at its cap and the oldest fade away", () => {
  const g = fresh({ max: 10 });
  run(g, 300);
  assert.equal(g.pile.length, 10);
  assert.ok(g.leaves.length < 30, `${g.leaves.length} leaves kept`);
});

test("a shake throws the whole pile up, and it settles again", () => {
  const g = fresh();
  run(g, 120);
  const n = g.pile.length;
  g.shake(1);
  assert.equal(g.pile.length, 0);
  run(g, 0.5);
  assert.ok(g.leaves.some(l => l.y < 300), "nothing flew up");
  run(g, 60);
  assert.ok(g.pile.length >= n, `${g.pile.length} of ${n} back down`);
});

test("tilting slides the pile to the low side", () => {
  const g = fresh();
  run(g, 120);
  g.gx = 0.5;
  run(g, 10);
  const mean = g.pile.reduce((s, l) => s + l.dx, 0) / g.pile.length;
  assert.ok(mean > 300, `pile centered at ${mean}`);
});

test("the pile rides the floor when it moves (the phone's sheet)", () => {
  const g = fresh();
  run(g, 120);
  g.resize(400, 300);
  g.step(1 / 30);
  for (const l of g.pile) assert.ok(l.dy <= 300 && l.dy > 200, `resting at ${l.dy}`);
});

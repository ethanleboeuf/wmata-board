import test from "node:test";
import assert from "node:assert/strict";
import { mercator, unmercator, coverView, buildTrack, snapToTrack, pointAt, laneOffset,
         headingSign, kmToMerc, Glider } from "../../web/track.js";

const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);

test("mercator round trip", () => {
  const [x, y] = mercator(-77.08, 38.89);
  const [lon, lat] = unmercator(x, y);
  near(lon, -77.08, 1e-9); near(lat, 38.89, 1e-9);
  near(mercator(0, 0)[0], 0.5); near(mercator(0, 0)[1], 0.5);
});

test("coverView covers the panel", () => {
  const bbox = [-77.122, 38.844, -76.978, 38.966];
  const v = coverView(bbox, 883, 957);
  const [x0, y0] = mercator(bbox[0], bbox[3]), [x1, y1] = mercator(bbox[2], bbox[1]);
  const px = 512 * 2 ** v.zoom;
  assert.ok((x1 - x0) * px >= 883 - 1e-6 && (y1 - y0) * px >= 957 - 1e-6);
  assert.ok(Math.abs((x1 - x0) * px - 883) < 1e-6 || Math.abs((y1 - y0) * px - 957) < 1e-6);
  near(v.center[0], -77.05, 1e-9);
});

const line = buildTrack([[-77.1, 38.9], [-77.0, 38.9], [-77.0, 39.0]]);

test("buildTrack arc length", () => {
  assert.equal(line.pts.length, 3);
  near(line.cum[0], 0);
  near(line.length, line.cum[2]);
  assert.ok(line.cum[1] > 0 && line.cum[2] > line.cum[1]);
});

test("snap and pointAt are inverse along the track", () => {
  const p = pointAt(line, line.cum[1] / 2);
  const { s, dist } = snapToTrack(line, [p.x, p.y + 1e-6]);
  near(s, line.cum[1] / 2, 1e-9);
  assert.ok(dist < 2e-6);
  near(p.dx, 1); near(p.dy, 0);
  const end = pointAt(line, 99);
  near(end.x, line.pts[2][0]); near(end.y, line.pts[2][1]);
  const start = pointAt(line, -5);
  near(start.x, line.pts[0][0]);
});

test("laneOffset shifts perpendicular", () => {
  const out = laneOffset([[0, 0], [10, 0]], 3);
  assert.deepEqual(out, [[0, 3], [10, 3]]);
  assert.deepEqual(laneOffset([[0, 0], [10, 0]], 0), [[0, 0], [10, 0]]);
});

test("headingSign from bearing vs track direction (track runs east here)", () => {
  const s = line.cum[1] / 2;
  assert.equal(headingSign(line, s, 90), 1);     // heading east = along the track
  assert.equal(headingSign(line, s, 270), -1);
  assert.equal(headingSign(line, s, 0), 0);      // perpendicular: unknown
  assert.equal(headingSign(line, s, null), 0);
});

test("glider interpolates between snapshots over the feed interval", () => {
  const g = new Glider({ fadeMs: 1000 });
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 100, 0);
  assert.equal(g.at(0)[0].s, 0.00001);
  assert.equal(g.at(0)[0].opacity, 1);                 // first snapshot shows at once
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 105, 10_000);   // < 1 km: glides
  near(g.at(10_000)[0].s, 0.00001);
  near(g.at(12_500)[0].s, 0.000015);
  near(g.at(20_000)[0].s, 0.00002);
});

test("glider continues from where it is drawn when a snapshot lands mid-glide", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 110, 0);   // 10 s glide
  g.update([{ id: "a", line: "OR", s: 0.00003, dir: 1 }], 115, 5000); // mid-way: drawn at 0.00001
  near(g.at(5000)[0].s, 0.00001);
  near(g.at(10_000)[0].s, 0.00003);
});

test("repeated feed timestamp is ignored (review focus 4)", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 105, 1000);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 1 }], 105, 3000);   // same snapshot again
  near(g.at(3500)[0].s, 0.00001 * 0.5);
});

test("timestamp going backwards (fixture wrap) snaps instead of gliding", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 1 }], 200, 0);
  g.update([{ id: "a", line: "OR", s: 0.0, dir: 1 }], 100, 1000);
  near(g.at(1000)[0].s, 0.0);
});

test("jumps over ~1 km and line changes snap", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }, { id: "b", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "a", line: "OR", s: kmToMerc(3), dir: 1 }, { id: "b", line: "SV", s: 0.00001, dir: 1 }], 105, 1000);
  near(g.at(1000).find(v => v.id === "a").s, kmToMerc(3));
  const b = g.at(1000).find(v => v.id === "b");
  assert.equal(b.line, "SV"); near(b.s, 0.00001);
});

test("vehicles that vanish fade out, new ones fade in", () => {
  const g = new Glider({ fadeMs: 1000 });
  g.update([{ id: "a", line: "OR", s: 0, dir: 1 }], 100, 0);
  g.update([{ id: "b", line: "OR", s: 0, dir: 1 }], 105, 1000);
  const a = g.at(1500).find(v => v.id === "a"), b = g.at(1500).find(v => v.id === "b");
  near(a.opacity, 0.5); near(b.opacity, 0.5);
  assert.equal(g.at(2100).find(v => v.id === "a"), undefined);
});

test("direction falls back to movement, then to the last known", () => {
  const g = new Glider();
  g.update([{ id: "a", line: "OR", s: 0.00002, dir: 0 }], 100, 0);
  assert.equal(g.at(0)[0].dir, 1);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 0 }], 105, 1000);
  assert.equal(g.at(1000)[0].dir, -1);
  g.update([{ id: "a", line: "OR", s: 0.00001, dir: 0 }], 110, 2000);
  assert.equal(g.at(2000)[0].dir, -1);
});

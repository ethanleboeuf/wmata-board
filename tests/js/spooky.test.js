import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spookyStyle, cobweb, jackOLantern, SPOOKY_LAND } from "../../web/spooky.js";

const style = JSON.parse(readFileSync(new URL("../../web/style.json", import.meta.url), "utf-8"));
const byId = s => Object.fromEntries(s.layers.map(l => [l.id, l]));

test("spookyStyle retints the basemap and leaves the original alone", () => {
  const before = JSON.stringify(style);
  const out = byId(spookyStyle(style));
  assert.equal(JSON.stringify(style), before);
  assert.equal(out.background.paint["background-color"], SPOOKY_LAND);
  assert.equal(out.earth.paint["fill-color"], SPOOKY_LAND);
  assert.equal(out["roads-major"].paint["line-color"], "#b8581c");
  assert.deepEqual(out["roads-major"].filter, byId(style)["roads-major"].filter);
});

test("spookyStyle puts an orange glow just under the major roads", () => {
  const ids = spookyStyle(style).layers.map(l => l.id);
  assert.equal(ids.indexOf("roads-major-glow") + 1, ids.indexOf("roads-major"));
  assert.equal(ids.length, style.layers.length + 1);
});

test("station art is well-formed SVG with no NaNs", () => {
  for (const svg of [cobweb(100, 200), jackOLantern(100.25, 200.75)]) {
    assert.ok(!svg.includes("NaN"));
    assert.equal((svg.match(/</g) || []).length, (svg.match(/>/g) || []).length);
  }
  assert.match(cobweb(100, 200), /^<path class="cobweb" d="M85\.0,185\.0 L104\.0,185\.0/);
});

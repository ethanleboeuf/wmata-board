import test from "node:test";
import assert from "node:assert/strict";
import { waveShown, waveHtml, bubbleLines } from "../../web/wave.js";

const at = (h, m = 0) => new Date(2026, 9, 27, h, m);

test("they wave only while she's riding, and only in the morning", () => {
  assert.equal(waveShown("trip-1", at(7, 45)), true);
  assert.equal(waveShown("trip-1", at(11, 59)), true);
  assert.equal(waveShown("trip-1", at(12, 0)), false);
  assert.equal(waveShown("trip-1", at(17, 10)), false);
  assert.equal(waveShown(null, at(7, 45)), false);
});

test("the bubble wraps into short lines", () => {
  assert.deepEqual(bubbleLines("have a good day at work!"), ["have a good", "day at work!"]);
  assert.deepEqual(bubbleLines("hi!"), ["hi!"]);
  assert.deepEqual(bubbleLines("supercalifragilistic"), ["supercalifragilistic"]);
});

test("the pair and their bubble are well-formed SVG, escaped, with no NaNs", () => {
  const svg = waveHtml(100.25, 200.75, "have a <ok> day at work!");
  assert.ok(!svg.includes("NaN"));
  assert.equal((svg.match(/</g) || []).length, (svg.match(/>/g) || []).length);
  assert.match(svg, /^<g class="wave-home"/);
  assert.match(svg, /&lt;ok&gt;/);
  assert.match(svg, /class="man"/);
  assert.match(svg, /class="dog"/);
  assert.equal((svg.match(/<tspan /g) || []).length, 2);
});

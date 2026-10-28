import test from "node:test";
import assert from "node:assert/strict";
import { waveMode, waveHtml, cheerHtml, confetti, bubbleLines, textPx } from "../../web/wave.js";

const at = (h, m = 0) => new Date(2026, 9, 27, h, m);

test("they wave her off on a morning ride and cheer her home on an afternoon one", () => {
  assert.equal(waveMode("trip-1", at(7, 45)), "wave");
  assert.equal(waveMode("trip-1", at(11, 59)), "wave");
  assert.equal(waveMode("trip-1", at(12, 0)), "cheer");
  assert.equal(waveMode("trip-1", at(17, 10)), "cheer");
  assert.equal(waveMode(null, at(7, 45)), null);
  assert.equal(waveMode(null, at(17, 10)), null);
  assert.equal(waveMode(undefined, at(17, 10)), null);
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

test("the cheer is well-formed SVG: a dancing pair, confetti, the bubble on top", () => {
  const svg = cheerHtml(100.25, 200.75, "YAYAYAYAYAY");
  assert.ok(!svg.includes("NaN"));
  assert.equal((svg.match(/</g) || []).length, (svg.match(/>/g) || []).length);
  assert.match(svg, /^<g class="wave-home cheer"/);
  assert.match(svg, /class="man dance"/);
  assert.match(svg, /class="dog"/);
  assert.match(svg, /YAYAYAYAYAY/);
  assert.ok((svg.match(/class="confetti"/g) || []).length >= 20);
  assert.ok(svg.lastIndexOf('class="confetti"') < svg.indexOf('class="bubble"'));
});

test("capitals get a wider bubble", () => {
  assert.ok(textPx("YAYAYAYAYAY") > textPx("yayayayayay") + 20);
});

test("confetti is the same every redraw, so a pan doesn't reshuffle it", () => {
  assert.equal(confetti(10, 20), confetti(10, 20));
  assert.notEqual(confetti(10, 20), confetti(11, 20));   // but it moves with the spot
});

test("he wears a Nationals jersey and the dog a space collar, morning and afternoon", () => {
  for (const svg of [waveHtml(100, 200, "hi"), cheerHtml(100, 200, "YAY")]) {
    assert.match(svg, /class="jersey"/);
    assert.match(svg, /class="curly-w"/);
    assert.match(svg, /class="collar"/);
    assert.match(svg, /class="planet"/);
    assert.match(svg, /class="star"/);
    assert.equal((svg.match(/class="sleeve"/g) || []).length, 2);
  }
});

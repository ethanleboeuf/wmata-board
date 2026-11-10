import test from "node:test";
import assert from "node:assert/strict";
import { HELLO_SHOW_S, BURST_S, shouldPlay, remainingS, burstSpecs, burstHtml, bubblePlace, bubbleHtml } from "../../web/hello.js";

const hello = (over = {}) => ({ id: 7, emoji: "💗", text: "", age_s: 2, ...over });

test("a hello plays once: a new id that is still showing", () => {
  assert.equal(shouldPlay(hello(), null), true);
  assert.equal(shouldPlay(hello(), 6), true);
  assert.equal(shouldPlay(hello(), 7), false);          // the 5 s poll again
  assert.equal(shouldPlay(null, null), false);
  assert.equal(shouldPlay({ ...hello(), id: undefined }, null), false);
  assert.equal(shouldPlay(hello({ age_s: 59.9 }), null), true);   // a page that loads mid-show
  assert.equal(shouldPlay(hello({ age_s: 60 }), null), false);
});

test("the bubble stays for what's left of the minute, at least a second", () => {
  assert.equal(HELLO_SHOW_S, 60);
  assert.equal(remainingS(hello({ age_s: 0 })), 60);
  assert.equal(remainingS(hello({ age_s: 45.5 })), 14.5);
  assert.equal(remainingS(hello({ age_s: 59.9 })), 1);
});

test("a burst is a dozen varied emoji that start staggered and finish in about six seconds", () => {
  const specs = burstSpecs(7);
  assert.equal(specs.length, 12);
  assert.deepEqual(burstSpecs(7), specs);               // same id, same burst
  assert.notDeepEqual(burstSpecs(8), specs);
  assert.ok(new Set(specs.map(s => s.size)).size > 6);
  assert.ok(specs.some(s => s.dx < 0) && specs.some(s => s.dx > 0));
  for (const s of specs) {
    assert.ok(s.size >= 18 && s.size <= 44);
    assert.ok(s.rise >= 90 && s.rise <= 220);
    assert.ok(Math.abs(s.dx) <= 50);
    assert.ok(s.delay >= 0 && s.delay + s.dur <= BURST_S + 0.001);
  }
  assert.ok(Math.max(...specs.map(s => s.delay + s.dur)) > BURST_S - 1);
  assert.equal(burstSpecs(7, 4).length, 4);
});

test("burstHtml puts each emoji at the origin with its own sizes and timing, escaped", () => {
  const html = burstHtml("💗", 120.46, 80, burstSpecs(7, 3));
  assert.equal(html.match(/class="hello-bit"/g).length, 3);
  assert.equal(html.match(/💗/g).length, 3);
  assert.match(html, /left:120\.5px;top:80\.0px/);
  assert.match(html, /--dx:-?\d+(\.\d)?px/);
  assert.match(html, /animation-duration:\d\.\d\ds/);
  assert.equal(burstHtml("<b>", 0, 0, burstSpecs(1, 1)).includes("<b>"), false);
});

test("the bubble sits to the right of the origin unless that runs off the map", () => {
  assert.deepEqual(bubblePlace(100, 80, 400), { left: 124, side: "right" });
  assert.deepEqual(bubblePlace(380, 80, 400), { left: 276, side: "left" });
  assert.equal(bubblePlace(30, 500, 400).left, 8);       // too wide either way: pinned to the edge
});

test("the bubble wraps her words, escapes them, and lasts the remaining time", () => {
  const html = bubbleHtml(100, 200, "see you <i>soon</i> at home", 12.5, 400);
  assert.match(html, /class="hello-bubble right"/);
  assert.match(html, /--show:12\.5s/);
  assert.equal(html.includes("<i>"), false);
  assert.match(html, /&lt;i&gt;/);
  assert.ok(html.split("<br>").length >= 2);            // wrapped by wave.js's bubbleLines
  assert.equal(bubbleHtml(100, 200, "", 12, 400), "");
  assert.equal(bubbleHtml(100, 200, "   ", 12, 400), "");
});

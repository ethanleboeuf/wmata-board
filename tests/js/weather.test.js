import test from "node:test";
import assert from "node:assert/strict";
import { weatherHeaderHtml, weatherHintsHtml } from "../../web/weather.js";

const rainy = { temp: 41, feels: 35, icon: "🌧", text: "Rain", hint: "☔ Rain likely by 8 AM",
                hints: ["☔ Rain likely by 8 AM", "🧥 Feels like 35°"] };
const mild = { temp: 68, feels: 68, icon: "☀️", text: "Clear", hint: null, hints: [] };

test("nothing without weather", () => {
  assert.equal(weatherHeaderHtml(null), "");
  assert.equal(weatherHeaderHtml(undefined, { hint: true }), "");
  assert.equal(weatherHintsHtml(null), "");
  assert.equal(weatherHintsHtml(mild), "");
});

test("header: icon and temperature, with the text as the tooltip", () => {
  const html = weatherHeaderHtml(rainy);
  assert.match(html, /🌧/);
  assert.match(html, /41°/);
  assert.match(html, /title="Rain"/);
  assert.doesNotMatch(html, /Rain likely/);
});

test("header: the wall adds the hint, dimmer, when there is one", () => {
  assert.match(weatherHeaderHtml(rainy, { hint: true }), /class="wx-hint">☔ Rain likely by 8 AM</);
  assert.doesNotMatch(weatherHeaderHtml(mild, { hint: true }), /wx-hint/);
});

test("hints: both, as one line", () => {
  const html = weatherHintsHtml(rainy);
  assert.match(html, /☔ Rain likely by 8 AM/);
  assert.match(html, /🧥 Feels like 35°/);
  assert.equal(weatherHintsHtml({ ...rainy, hints: ["💨 Windy"] }).includes("Rain"), false);
});

test("interpolated text is escaped", () => {
  const evil = { temp: 1, feels: 1, icon: "<b>", text: `"x"`, hint: "<img onerror=1>", hints: ["<script>", "&"] };
  for (const html of [weatherHeaderHtml(evil, { hint: true }), weatherHintsHtml(evil)]) {
    assert.doesNotMatch(html, /<(b|img|script)\b/);
  }
  assert.match(weatherHintsHtml(evil), /&lt;script&gt;/);
  assert.match(weatherHeaderHtml(evil), /title="&quot;x&quot;"/);
});

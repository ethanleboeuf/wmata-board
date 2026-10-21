import test from "node:test";
import assert from "node:assert/strict";
import { arrivalsHtml, chip } from "../../web/render.js";

const board = (over = {}) => ({
  notice: null,
  platforms: [
    { group: "1", label: "To Washington · New Carrollton", trains: [
      { line: "SV", cars: 6, destination: "New Carrollton", minutes: 0, display: "BRD" },
      { line: "OR", cars: 8, destination: "New Carrollton", minutes: 9, display: "9" },
      { line: "OR", cars: null, destination: "<b>x</b>", minutes: null, display: "—" }] },
    { group: "2", label: "To Vienna · Ashburn", trains: [] }],
  ...over,
});

test("rows render chip, destination, cars and minutes", () => {
  const html = arrivalsHtml(board());
  assert.match(html, /To Washington · New Carrollton/);
  assert.match(html, /class="min now">BRD</);
  assert.match(html, /9<small>min<\/small>/);
  assert.match(html, /6 car/);
  assert.match(html, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.doesNotMatch(html, /null car/);
});

test("empty platform says so", () => {
  assert.match(arrivalsHtml(board()), /No trains predicted/);
});

test("notice replaces the rows", () => {
  const html = arrivalsHtml(board({ notice: "No trains · service resumes 5:19 AM" }));
  assert.match(html, /class="notice"/);
  assert.match(html, /service resumes 5:19 AM/);
  assert.doesNotMatch(html, /class="row"/);
});

test("chip uses line colors", () => {
  assert.equal(chip("OR"), '<span class="chip" style="background:#ed8b00;color:#111">OR</span>');
  assert.match(chip("ZZ"), /background:#3b4a5e/);
});

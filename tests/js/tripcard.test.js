import test from "node:test";
import assert from "node:assert/strict";
import { tripHtml, trainCardHtml, commuteCardHtml, commuteAmHtml } from "../../web/render.js";
import { delayText } from "../../web/format.js";

const stop = (code, name, time) => ({ code, name, time, t: 0 });
const SV = { id: "sv1", line: "SV", destination: "Largo", cars: 6, delay_s: 180, live: true,
  stops: [stop("K01", "Court House", "7:41"), stop("C04", "Foggy Bottom", "7:47"), stop("C01", "Metro Center", "7:52"),
          stop("D01", "Federal Triangle", null), stop("D02", "Smithsonian", "7:55"), stop("G05", "Largo", "8:40")] };
const RD = { id: "r1", line: "RD", destination: "Glenmont", cars: null, delay_s: null, live: false,
  stops: [stop("A01", "Metro Center", "7:56"), stop("B05", "Brookland-CUA", "8:08")] };

test("delay text", () => {
  assert.deepEqual([null, undefined, 20, 180, -130].map(delayText), ["", "", "On time", "3 min late", "2 min early"]);
});

test("a map train: header, meta and the next five stops", () => {
  const html = tripHtml(SV);
  assert.match(html, /<span class="tdest">To Largo<\/span>/);
  assert.match(html, /6 cars · 3 min late · live/);
  assert.equal((html.match(/class="tstop[ "]/g) || []).length, 5);
  assert.match(html, /Federal Triangle<\/span><span class="ttime">—/);
  assert.doesNotMatch(html, /8:40/);
});

test("a commute leg shows boarding to alighting, both ends marked", () => {
  const html = tripHtml(SV, { from: "K01", to: "C01" });
  assert.equal((html.match(/class="tstop[ "]/g) || []).length, 3);
  assert.equal((html.match(/class="tstop end"/g) || []).length, 2);
  assert.doesNotMatch(html, /Smithsonian/);
  assert.match(tripHtml(RD), /timetable/);
  assert.doesNotMatch(tripHtml(RD), /cars/);
});

test("a map train without predictions still says what it is", () => {
  const html = trainCardHtml({ id: "v1", line: "OR", cars: 8, trip_id: "x" }, null);
  assert.match(html, /chip.*OR/);
  assert.match(html, /8 cars/);
  assert.match(html, /No stop predictions for this train/);
});

const amRow = { line: "SV", leave: "7:41", mc_arrive: "7:52", red_leave: "7:56", mc_wait: 4, brookland: "8:08",
  shuttle: "8:12", spare: 4, target: true, late: false, live: true,
  legs: [{ trip: "sv1", line: "SV", from: "K01", to: "C01" }, { trip: "r1", line: "RD", from: "A01", to: "B05" }] };

test("a morning commute card: both legs, transfer and shuttle", () => {
  const html = commuteCardHtml(amRow, "am", [SV, RD]);
  assert.match(html, /<h3>Leave 7:41 → shuttle 8:12<\/h3>/);
  assert.match(html, /Metro Center · 4 min wait/);
  assert.match(html, /Brookland 8:08 → shuttle 8:12 \(\+4\)/);
  assert.ok(html.indexOf("To Largo") < html.indexOf("To Glenmont"));
});

test("legs loading, or failed", () => {
  assert.equal((commuteCardHtml(amRow, "am", [undefined, undefined]).match(/Loading…/g) || []).length, 2);
  assert.match(commuteCardHtml(amRow, "am", [SV, null]), /Details unavailable/);
});

test("evening from the hospital starts with the shuttle", () => {
  const row = { shuttle: "5:06", brookland: "5:16", red_leave: "5:21", mc_wait: 3, home: "5:45", legs: amRow.legs };
  const html = commuteCardHtml(row, "hospital", [RD, SV]);
  assert.match(html, /<h3>Shuttle 5:06 → home 5:45<\/h3>/);
  assert.match(html, /Shuttle 5:06 → Brookland 5:16/);
  assert.doesNotMatch(commuteCardHtml(row, "station", [RD, SV]), /Shuttle 5:06 → Brookland/);
});

test("commute rows carry their index for tapping", () => {
  const html = commuteAmHtml({ name: "CN", notice: null, am: { shuttles: [], rows: [amRow, amRow] } });
  assert.match(html, /data-i="0" class="crow am target"/);
  assert.match(html, /data-i="1" class="crow am target"/);
});

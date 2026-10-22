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

test("morning-to-Takoma card heading", () => {
  const row = { leave: "7:45", arrive: "8:14", mc_wait: 3, legs: amRow.legs };
  assert.match(commuteCardHtml(row, "am-station", [null, null], "Takoma"), /<h3>Leave 7:45 → Takoma 8:14<\/h3>/);
});

test("easter-egg ride plan: switches at Metro Center, gets off at the end", async () => {
  const { ridePlan, RIDE_MAX_S } = await import("../../web/format.js");
  const legs = [{ trip: "or", to: "C01" }, { trip: "rd", to: "B05" }];
  const t1 = { stops: [{ code: "K01", t: 1000 }, { code: "C01", t: 1600 }] };
  const t2 = { stops: [{ code: "A01", t: 1800 }, { code: "B05", t: 2500 }] };
  assert.deepEqual(ridePlan(legs, [t1, t2], 900), { trips: ["or", "rd"], switch_at: 1600, until: 2620 });
  // already past the transfer: straight onto the second train
  assert.equal(ridePlan(legs, [{ stops: [] }, t2], 1700).switch_at, 1700);
  // a map train, or nothing known: one trip for up to 3 h
  assert.deepEqual(ridePlan([{ trip: "x", to: null }], [null], 10), { trips: ["x"], switch_at: null, until: 10 + RIDE_MAX_S });
});

test("station picker: search, nearest, rows", async () => {
  const { matchStations, nearestStation, stationRowsHtml } = await import("../../web/render.js");
  const st = [{ codes: ["K01"], name: "Court House", lon: -77.085, lat: 38.891 },
              { codes: ["A01", "C01"], name: "Metro Center", lon: -77.028, lat: 38.898 },
              { codes: ["B05"], name: "Brookland-CUA", lon: -76.994, lat: 38.933 }];
  assert.deepEqual(matchStations(st, "").map(s => s.name), ["Brookland-CUA", "Court House", "Metro Center"]);
  assert.deepEqual(matchStations(st, " metro ").map(s => s.name), ["Metro Center"]);
  assert.equal(nearestStation(st, -77.03, 38.90).name, "Metro Center");
  const html = stationRowsHtml(st, "C01");
  assert.match(html, /<div class="prow"><button class="pname" data-code="K01">Court House<\/button><button class="pstar" data-fav="K01"[^>]*>☆/);
  assert.match(html, /<div class="prow on"><button class="pname" data-code="A01">Metro Center<\/button>/);
  assert.match(stationRowsHtml([], "K01"), /No matching station/);
});

test("station search forgives punctuation, abbreviations and nicknames", async () => {
  const { matchStations, pickerListHtml } = await import("../../web/render.js");
  const st = ["L'Enfant Plaza", "Gallery Place", "King St-Old Town", "Foggy Bottom-GWU", "Federal Triangle",
              "Federal Center SW", "Ronald Reagan Washington National Airport", "Court House"]
    .map((name, i) => ({ codes: [`X${String(i).padStart(2, "0")}`], name }));
  const names = q => matchStations(st, q).map(s => s.name);
  for (const q of ["lenfant", "L’Enfant", "l enfant", "LENF", "enfant", "plaza"]) assert.deepEqual(names(q), ["L'Enfant Plaza"], q);
  assert.deepEqual(names("chinatown"), ["Gallery Place"]);
  assert.deepEqual(names("king street"), ["King St-Old Town"]);
  assert.deepEqual(names("gwu"), ["Foggy Bottom-GWU"]);
  assert.deepEqual(names("dca"), ["Ronald Reagan Washington National Airport"]);
  assert.deepEqual(names("fed"), ["Federal Center SW", "Federal Triangle"]);
  assert.deepEqual(names("zzz"), []);
  const html = pickerListHtml(st, "", "X07", ["X07", "X00"]);
  assert.match(html, /^<div class="phead">Favorites<\/div><div class="prow on">.*Court House.*★.*L&#39;Enfant Plaza.*All stations/s);
  assert.doesNotMatch(pickerListHtml(st, "len", "X07", ["X07"]), /Favorites/);
});

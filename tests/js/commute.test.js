import test from "node:test";
import assert from "node:assert/strict";
import { commuteAmHtml, commutePmHtml } from "../../web/render.js";
import { waitClass } from "../../web/format.js";

const amRow = over => ({ line: "SV", leave: "7:38", door: "7:32", door_in: 5, mc_arrive: "7:49", red_leave: "7:51", mc_wait: 2,
  brookland: "8:03", shuttle: "8:06", spare: 3, target: false, live: true, ...over });
const am = (rows, over = {}) => ({ mode: "am", name: "Children's National", notice: null,
  am: { shuttles: ["8:12", "8:18"], rows }, ...over });

test("wait colours", () => {
  assert.deepEqual([1, 3, 4, 6, 7, 12].map(waitClass), ["w-short", "w-short", "w-mid", "w-mid", "w-long", "w-long"]);
});

test("morning rows: leave, wait, Brookland, shuttle + spare", () => {
  const html = commuteAmHtml(am([amRow(), amRow({ leave: "7:45", line: "OR", mc_wait: 7, shuttle: "8:18", target: true, live: false }),
    amRow({ shuttle: "8:30" })]));
  assert.match(html, /Children&#39;s National · shuttle 8:12 \/ 8:18/);
  assert.match(html, /<span class="ct">7:32<small>7:38<\/small><\/span><span class="cw w-short">2<small>min<\/small><\/span>/);
  assert.match(html, /<span class="cs">8:06<small>\+3<\/small><\/span>/);
  assert.match(html, /crow am target">.*?7:45.*?w-long.*?<span class="sched">sched<\/span>/);
  assert.match(html, /<div data-i="2" class="crow am">/);   // after the targets: shown as normal
  assert.equal((html.match(/class="sched"/g) || []).length, 1);
});

test("the row she's riding is marked, with her in place of the sched tag", () => {
  const html = commuteAmHtml(am([amRow({ riding: true, target: true, live: false }), amRow()]));
  assert.match(html, /<div data-i="0" class="crow am target riding">.*?<span class="rtag" title="Riding">🙋<\/span><\/div>/);
  assert.doesNotMatch(html, /class="sched"/);
  assert.match(html, /<div data-i="1" class="crow am">/);
  const evening = commutePmHtml({ ...pm, pm: { ...pm.pm, hospital: [{ ...pm.pm.hospital[0], riding: true }] } }, "hospital");
  assert.match(evening, /class="crow pm riding">.*?🙋/);
});

test("each morning row leads with when to leave home, then the train", () => {
  const html = commuteAmHtml(am([amRow()]));
  assert.match(html, /<span>Home · train<\/span>/);
  assert.match(html, /<span class="ct">7:32<small>7:38<\/small><\/span>/);
});

test("rows she can no longer make from home are dimmed, not dropped", () => {
  const html = commuteAmHtml(am([amRow({ door_in: -1 }), amRow({ door_in: 0 })]));
  assert.match(html, /<div data-i="0" class="crow am late">/);
  assert.match(html, /<div data-i="1" class="crow am">/);
  // the row she's on is never dimmed
  assert.match(commuteAmHtml(am([amRow({ door_in: -9, riding: true })])), /class="crow am riding"/);
});

const lead = html => (html.match(/<div class="cleave">(.*?)<\/div>/) || [])[1];

test("headline: the first target-shuttle row she can still make", () => {
  const html = commuteAmHtml(am([amRow({ door_in: -1, target: true, door: "7:29", shuttle: "8:12" }),
    amRow({ door_in: 2, door: "7:32" }),
    amRow({ door_in: 4, target: true, door: "7:34", shuttle: "8:12" }),
    amRow({ door_in: 7, target: true, door: "7:37", shuttle: "8:18" })]));
  assert.equal(lead(html), "Leave home <b>7:34</b> · in 4 min → 8:12 shuttle");
});

test("headline: falls back to the first makeable row, says now, and goes away while riding", () => {
  assert.equal(lead(commuteAmHtml(am([amRow({ door_in: -2 }), amRow({ door_in: 1, door: "7:40", shuttle: "8:24" })]))),
    "Leave home <b>7:40</b> · in 1 min → 8:24 shuttle");
  assert.equal(lead(commuteAmHtml(am([amRow({ door_in: 0, door: "7:40", target: true, shuttle: "8:12" })]))),
    "Leave home <b>now</b> → 8:12 shuttle");
  assert.equal(lead(commuteAmHtml(am([amRow({ door_in: -3 })]))), undefined);
  assert.equal(lead(commuteAmHtml(am([amRow({ riding: true, door_in: -3 }), amRow({ door_in: 4, target: true })]))), undefined);
});

test("headline to the station ends at its arrival", () => {
  const c = am([], { am: { shuttles: ["8:12"], rows: [], station_name: "Takoma",
    station: [{ ...amRow({ door_in: 3, door: "7:35" }), arrive: "8:05" }] } });
  assert.equal(lead(commuteAmHtml(c, "station", { tabs: true })), "Leave home <b>7:35</b> · in 3 min → Takoma 8:05");
});

test("morning notice and empty states", () => {
  assert.match(commuteAmHtml(am([], { notice: "Commute times unavailable" })), /Commute times unavailable/);
  assert.match(commuteAmHtml(am([])), /No connections found/);
});

const pm = { mode: "pm", name: "Children's National", notice: null, pm: {
  station_name: "Takoma",
  hospital: [{ shuttle: "5:06", brookland: "5:16", red_leave: "5:21", mc_arrive: "5:32", line: "OR", mc_wait: 3, home: "5:45", live: true }],
  station: [{ red_leave: "5:08", mc_arrive: "5:24", line: "SV", mc_wait: 2, home: "5:36", live: false }] } };

test("evening from the hospital", () => {
  const html = commutePmHtml(pm, "hospital");
  assert.match(html, /<button class="ctab on" data-origin="hospital">Hospital<\/button>/);
  assert.match(html, /<button class="ctab" data-origin="station">Takoma<\/button>/);
  assert.match(html, /<span class="ct">5:06<\/span><span class="ct dim">5:21<\/span><span class="cw w-short">3/);
  assert.match(html, /<span class="ct">5:45<\/span><\/div>/);
  assert.doesNotMatch(html, /5:08/);
});

test("evening from the station", () => {
  const html = commutePmHtml(pm, "station");
  assert.match(html, /class="ctab on" data-origin="station">Takoma/);
  assert.match(html, /<span class="ct">5:08<\/span><span class="cw w-short">2.*5:36.*sched/);
  assert.doesNotMatch(html, /5:06/);
});

test("commute alerts join the board's, each once", async () => {
  const { mergeAlerts } = await import("../../web/format.js");
  const a = id => ({ id, lines: ["OR"], text: id, updated: "" });
  assert.deepEqual(mergeAlerts([a("1"), a("2")], [a("2"), a("3")]).map(x => x.id), ["1", "2", "3"]);
  assert.deepEqual(mergeAlerts([a("1")], undefined).map(x => x.id), ["1"]);
  assert.deepEqual(mergeAlerts(undefined, null), []);
});

test("phone morning: hospital/Takoma tabs and Takoma rows", async () => {
  const { commuteModeHtml } = await import("../../web/render.js");
  const c = am([amRow()]);
  c.am.station_name = "Takoma";
  c.am.station = [{ line: "OR", leave: "7:45", mc_arrive: "7:55", red_leave: "7:58", mc_wait: 3, arrive: "8:14", live: false }];
  assert.doesNotMatch(commuteAmHtml(c), /ctab/);   // the wall: no tabs
  const hosp = commuteAmHtml(c, "hospital", { tabs: true });
  assert.match(hosp, /class="ctab on" data-dest="hospital">Children&#39;s National/);
  assert.match(hosp, /8:06<small>\+3/);
  const tak = commuteAmHtml(c, "station", { tabs: true });
  assert.match(tak, /class="ctab on" data-dest="station">Takoma/);
  assert.match(tak, /crow am station">.*?7:45.*?w-short.*?<span class="ct dim">7:58<\/span><span class="ct">8:14<\/span>.*?sched/);
  assert.doesNotMatch(tak, /8:06/);
  assert.match(commuteModeHtml("pm"), /class="ctab" data-mode="am">Morning.*class="ctab on" data-mode="pm">Evening/);
});

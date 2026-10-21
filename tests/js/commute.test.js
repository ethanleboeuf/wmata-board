import test from "node:test";
import assert from "node:assert/strict";
import { commuteAmHtml, commutePmHtml } from "../../web/render.js";
import { waitClass } from "../../web/format.js";

const amRow = over => ({ line: "SV", leave: "7:38", mc_arrive: "7:49", red_leave: "7:51", mc_wait: 2,
  brookland: "8:03", shuttle: "8:06", spare: 3, target: false, late: false, live: true, ...over });
const am = (rows, over = {}) => ({ mode: "am", name: "Children's National", notice: null,
  am: { shuttles: ["8:12", "8:18"], rows }, ...over });

test("wait colours", () => {
  assert.deepEqual([1, 3, 4, 6, 7, 12].map(waitClass), ["w-short", "w-short", "w-mid", "w-mid", "w-long", "w-long"]);
});

test("morning rows: leave, wait, Brookland, shuttle + spare", () => {
  const html = commuteAmHtml(am([amRow(), amRow({ leave: "7:45", line: "OR", mc_wait: 7, shuttle: "8:18", target: true, live: false }),
    amRow({ shuttle: "8:30", late: true })]));
  assert.match(html, /Children&#39;s National · shuttle 8:12 \/ 8:18/);
  assert.match(html, /<span class="ct">7:38<\/span><span class="cw w-short">2<small>min<\/small><\/span>/);
  assert.match(html, /<span class="cs">8:06<small>\+3<\/small><\/span>/);
  assert.match(html, /crow am target">.*?7:45.*?w-long.*?<span class="sched">sched<\/span>/);
  assert.match(html, /crow am late">/);
  assert.equal((html.match(/class="sched"/g) || []).length, 1);
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

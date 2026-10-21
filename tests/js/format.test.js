import test from "node:test";
import assert from "node:assert/strict";
import { minuteParts, pillState, formatClock, alertIndex, escapeHtml, arrivalsExpired, liveLabel, LINE_COLORS } from "../../web/format.js";

test("minuteParts", () => {
  assert.deepEqual(minuteParts("BRD"), { big: "BRD", unit: "", now: true });
  assert.deepEqual(minuteParts("ARR"), { big: "ARR", unit: "", now: true });
  assert.deepEqual(minuteParts("7"), { big: "7", unit: "min", now: false });
  assert.deepEqual(minuteParts("—"), { big: "—", unit: "", now: false });
  assert.deepEqual(minuteParts(undefined), { big: "—", unit: "", now: false });
});

test("pill hidden when fresh", () => {
  assert.equal(pillState({ nowMs: 10_000, lastOkMs: 9_000, startMs: 0, arrivalsAgeS: 20 }).kind, "hidden");
});

test("pill amber when arrivals older than 60 s, counting time since last response", () => {
  const p = pillState({ nowMs: 100_000, lastOkMs: 95_000, startMs: 0, arrivalsAgeS: 58 });
  assert.equal(p.kind, "amber");
  assert.equal(p.text, "Updated 1 min ago");
  assert.equal(pillState({ nowMs: 0, lastOkMs: 0, startMs: 0, arrivalsAgeS: 185 }).text, "Updated 3 min ago");
});

test("pill red when backend unreachable for 15 s", () => {
  assert.deepEqual(pillState({ nowMs: 30_000, lastOkMs: 10_000, startMs: 0, arrivalsAgeS: 5 }),
                   { kind: "red", text: "Board offline" });
  // never reached since page start
  assert.equal(pillState({ nowMs: 16_000, lastOkMs: null, startMs: 0, arrivalsAgeS: null }).kind, "red");
  assert.equal(pillState({ nowMs: 5_000, lastOkMs: null, startMs: 0, arrivalsAgeS: null }).kind, "hidden");
});

test("formatClock in the board's timezone", () => {
  const d = new Date("2026-10-21T02:46:00Z");   // 10:46 PM EDT
  assert.equal(formatClock(d, "America/New_York"), "10:46 PM");
});

test("alertIndex rotates every 10 s", () => {
  assert.equal(alertIndex(0, 123), -1);
  assert.equal(alertIndex(1, 999_999), 0);
  assert.equal(alertIndex(3, 0), 0);
  assert.equal(alertIndex(3, 10_000), 1);
  assert.equal(alertIndex(3, 25_000), 2);
  assert.equal(alertIndex(3, 30_000), 0);
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<a href="x">&'</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;");
});

test("line colors cover all six lines", () => {
  assert.deepEqual(Object.keys(LINE_COLORS).sort(), ["BL", "GR", "OR", "RD", "SV", "YL"]);
});

test("arrivalsExpired after 10 minutes, counting time since the last response", () => {
  assert.equal(arrivalsExpired({ nowMs: 0, lastOkMs: 0, arrivalsAgeS: 600 }), false);
  assert.equal(arrivalsExpired({ nowMs: 0, lastOkMs: 0, arrivalsAgeS: 601 }), true);
  assert.equal(arrivalsExpired({ nowMs: 300_000, lastOkMs: 0, arrivalsAgeS: 295 }), false);
  assert.equal(arrivalsExpired({ nowMs: 306_000, lastOkMs: 0, arrivalsAgeS: 295 }), true);
  assert.equal(arrivalsExpired({ nowMs: 9e9, lastOkMs: null, arrivalsAgeS: null }), false);
  assert.equal(arrivalsExpired({ nowMs: 9e9, lastOkMs: 0, arrivalsAgeS: null }), false);
});

test("liveLabel", () => {
  assert.equal(liveLabel({ stale: false, count: 12 }), "LIVE · 12 TRAINS");
  assert.equal(liveLabel({ stale: true, count: 12 }), "POSITIONS STALE");
});

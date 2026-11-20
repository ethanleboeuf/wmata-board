import test from "node:test";
import assert from "node:assert/strict";
import { tileOptions, tileBoard, showCommute } from "../../web/tile.js";

test("tileOptions defaults to half and only quarter keeps a platform", () => {
  assert.deepEqual(tileOptions(""), { size: "half", platform: null });
  assert.deepEqual(tileOptions("?size=quarter&platform=2"), { size: "quarter", platform: "2" });
  assert.deepEqual(tileOptions("?size=bogus"), { size: "half", platform: null });
  assert.deepEqual(tileOptions("?size=half&platform=1"), { size: "half", platform: null });
  assert.deepEqual(tileOptions("?size=quarter"), { size: "quarter", platform: null });
});

const board = { platforms: [{ group: "1", label: "East", trains: [] }, { group: "2", label: "West", trains: [] }], notice: null };

test("tileBoard: quarter keeps one platform, half keeps both", () => {
  const q = tileBoard(board, { size: "quarter", platform: "1" });
  assert.deepEqual(q.platforms.map(p => p.group), ["1"]);
  assert.equal(q.notice, null);
  assert.deepEqual(tileBoard(board, { size: "half", platform: null }).platforms.map(p => p.group), ["1", "2"]);
  assert.deepEqual(tileBoard(board, { size: "quarter", platform: null }).platforms.length, 2);
});

test("showCommute: half in the morning only", () => {
  assert.equal(showCommute({ mode: "am" }, { size: "half" }), true);
  assert.equal(showCommute({ mode: "am" }, { size: "quarter" }), false);
  assert.equal(showCommute({ mode: "pm" }, { size: "half" }), false);
  assert.equal(showCommute(null, { size: "half" }), false);
});

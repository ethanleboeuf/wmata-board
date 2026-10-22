// Polls /api/commute for both pages and hands each change to `onChange`
// (null when there is no panel). Outside the windows the server answers
// {mode: null} without calling WMATA. Preview off-hours with the page URL:
// ?commute=am&at=7:30 (or commute=pm). `getMode` (the phone's Commute button)
// asks for a panel outside the windows; the page URL wins over it.
import { COMMUTE_EXPIRE_MS } from "./format.js";

const POLL_MS = 15000;

function commuteQuery(mode) {
  const page = new URLSearchParams(location.search), q = new URLSearchParams();
  if (page.get("commute") || mode) q.set("mode", page.get("commute") || mode);
  if (page.get("at")) q.set("at", page.get("at"));
  return q.toString() ? `?${q}` : "";
}

// /api/trip suffix: a commute preview's trips are looked up in the timetable at that time.
export function tripQuery() {
  const at = new URLSearchParams(location.search).get("at");
  return at ? `?at=${encodeURIComponent(at)}` : "";
}

export function startCommute(onChange, getMode = () => null) {
  let current = null, okMs = null, timer = null;
  const set = value => { current = value; onChange(value); };
  async function poll() {
    clearTimeout(timer);
    try {
      const r = await fetch(`/api/commute${commuteQuery(getMode())}`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      okMs = Date.now();
      set(body.mode ? body : null);
    } catch (err) {
      console.warn("commute poll failed", err);
      if (current && Date.now() - okMs > COMMUTE_EXPIRE_MS) set(null);
    } finally {
      timer = setTimeout(poll, POLL_MS);
    }
  }
  poll();
  return { poll };
}

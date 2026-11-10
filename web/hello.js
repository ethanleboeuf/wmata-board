// Her hello (the phone's 💗 button): a dozen of her emoji float up over the map
// and, if she typed a few words, a speech bubble stays beside them for the
// rest of the minute. Pure string/number helpers; map.js owns the layer and
// asks for HTML to drop in. Animated with transform and opacity only
// (keyframes in board.css), so it's cheap on the Pi.
import { escapeHtml } from "./format.js";
import { bubbleLines, textPx } from "./wave.js";

export const HELLO_SHOW_S = 60;   // matches hello.py: how long a hello is still showing
export const BURST_S = 6;         // the emoji are all gone by then
const COUNT = 12;
const LINE_PX = 15;

// Play it once: an id this page hasn't played, still within its minute (a page
// that loads mid-show plays it too).
export const shouldPlay = (hello, lastId) =>
  !!hello && hello.id !== undefined && hello.id !== lastId && hello.age_s < HELLO_SHOW_S;

// How long the bubble stays: what's left of the minute.
export const remainingS = hello => Math.max(1, HELLO_SHOW_S - hello.age_s);

// Where each emoji goes: drift sideways, rise, size, and when it starts. A
// seeded generator, so one hello is the same burst on the wall and the phone.
export function burstSpecs(id, count = COUNT) {
  let seed = (Math.abs(Number(id)) % 2147483646) + 1;
  const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const specs = [];
  for (let i = 0; i < count; i++) {
    const dur = 3.2 + rand() * 1.8;
    const delay = rand() * (BURST_S - dur);       // staggered, but done by BURST_S
    specs.push({
      dx: Math.round((rand() * 2 - 1) * 50), rise: Math.round(90 + rand() * 130),
      size: Math.round(18 + rand() * 26), delay, dur,
    });
  }
  return specs;
}

const f = v => v.toFixed(1);

// The emoji, all starting at (x, y) in the layer's px.
export const burstHtml = (emoji, x, y, specs) => specs.map(s =>
  `<div class="hello-bit" style="left:${f(x)}px;top:${f(y)}px;font-size:${s.size}px;` +
  `--dx:${s.dx}px;--rise:${s.rise}px;animation-duration:${s.dur.toFixed(2)}s;animation-delay:${s.delay.toFixed(2)}s">` +
  `${escapeHtml(emoji)}</div>`).join("");

// The bubble goes right of the origin, or left if that would run off the map.
export function bubblePlace(x, w, layerW) {
  const right = x + 24;
  if (right + w <= layerW - 8) return { left: right, side: "right" };
  const left = x - 24 - w;
  return left >= 8 ? { left, side: "left" } : { left: 8, side: "right" };
}

// Her words in a white bubble (same look as wave.js's) that fades in, holds,
// and fades out over `showS` seconds. "" when she wrote nothing.
export function bubbleHtml(x, y, text, showS, layerW) {
  const lines = bubbleLines(text);
  if (!lines.length) return "";
  const w = Math.round(Math.max(...lines.map(textPx)) + 20), h = lines.length * LINE_PX + 12;
  const { left, side } = bubblePlace(x, w, layerW);
  return `<div class="hello-bubble ${side}" style="left:${f(left)}px;top:${f(y - h / 2)}px;width:${w}px;` +
    `--show:${showS}s">${lines.map(escapeHtml).join("<br>")}</div>`;
}

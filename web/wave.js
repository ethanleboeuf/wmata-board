// Waving her off from home: while she's on a train in the morning (the phone's
// "I'm on this one"), a brunette man and his black dog stand near home on the
// map, waving, with a speech bubble. map.js places it at the config's
// [map.wave] point and redraws it with the static overlay (styled in board.css).
import { escapeHtml } from "./format.js";

const NOON = 12;
const LINE_CHARS = 12;      // the bubble wraps at about this many characters
const CHAR_PX = 7.4;        // 13px bold Inter, roughly
const LINE_PX = 15;

export const waveShown = (ride, now = new Date()) => ride !== null && ride !== undefined && now.getHours() < NOON;

export function bubbleLines(message) {
  const lines = [];
  for (const word of message.split(/\s+/).filter(Boolean)) {
    const last = lines.length - 1;
    if (last >= 0 && lines[last].length + 1 + word.length <= LINE_CHARS) lines[last] += ` ${word}`;
    else lines.push(word);
  }
  return lines;
}

// Ground at y=0, him at x=0, the dog to his right looking up at him.
const MAN = `<g class="man">` +
  `<path class="jeans" d="M-1.8,-11.5 L-2.4,0 M1.8,-11.5 L2.4,0"/>` +
  `<path class="shirt" d="M-4.2,-11 L-3.6,-20.4 Q0,-21.8 3.6,-20.4 L4.2,-11 Z"/>` +
  `<path class="skin" d="M3.6,-19.6 L5.6,-12.6"/>` +
  `<path class="wave skin" d="M-3.6,-19.6 L-7.6,-25.6"/>` +   // waving away from the bubble
  `<circle class="face" cx="0" cy="-24.8" r="3.6"/>` +
  `<path class="hair" d="M-3.8,-24.6 C-4.6,-29.8 3.8,-30.6 3.9,-25.4 C2.4,-27.8 -0.8,-27.9 -3,-26.4 Z"/>` +
  `<circle class="eye" cx="-1.3" cy="-24.6" r=".42"/><circle class="eye" cx="1.3" cy="-24.6" r=".42"/>` +
  `<path class="smile" d="M-1,-22.9 Q0,-22.1 1,-22.9"/>` +
  `</g>`;
const DOG = `<g class="dog">` +
  `<path class="leg" d="M8.8,-3.6 L8.6,0 M10.4,-3.6 L10.6,0 M14.4,-3.6 L14.2,0 M16,-3.6 L16.4,0"/>` +
  `<path class="tail" d="M16.8,-5.6 Q19.2,-6.8 19.4,-9.4"/>` +
  `<ellipse class="fur" cx="12.4" cy="-4.8" rx="4.8" ry="2.4"/>` +
  `<circle class="fur" cx="7.8" cy="-8" r="2.3"/>` +
  `<ellipse class="fur" cx="5.6" cy="-7.3" rx="1.5" ry="1.05"/>` +
  `<circle class="nose" cx="4.3" cy="-7.5" r=".5"/>` +
  `<path class="ear" d="M8.2,-9.8 Q10.2,-9.4 9.4,-6.6 Z"/>` +
  `<circle class="dogeye" cx="7.2" cy="-8.6" r=".42"/>` +
  `<path class="collar" d="M8.8,-6.2 L9.8,-8.6"/>` +
  `</g>`;

// (x, y): the [map.wave] point on screen. They stand just below it (home is a
// block from the station dot, which would cover them), the bubble at his head.
export function waveHtml(x, y, message) {
  const f = v => v.toFixed(1);
  const lines = bubbleLines(message);
  const w = Math.max(...lines.map(l => l.length)) * CHAR_PX + 20, h = lines.length * LINE_PX + 12;
  const bx = x + 28, by = y + 8;
  const text = lines.map((l, i) => `<tspan x="${f(bx + 10)}" dy="${i ? LINE_PX : 0}">${escapeHtml(l)}</tspan>`).join("");
  return `<g class="wave-home">` +
    `<g transform="translate(${f(x + 2)},${f(y + 92)}) scale(2.4)">${MAN}${DOG}</g>` +
    `<path class="bubble" d="M${f(bx + 1)},${f(by + 16)} L${f(x + 12)},${f(y + 32)} L${f(bx + 1)},${f(by + 24)} Z"/>` +
    `<rect class="bubble" x="${f(bx)}" y="${f(by)}" width="${f(w)}" height="${f(h)}" rx="10"/>` +
    `<text x="${f(bx + 10)}" y="${f(by + 19)}">${text}</text>` +
    `</g>`;
}

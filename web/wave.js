// Home, while she rides (the phone's "I'm on this one"): a brunette man and
// his black dog stand near home on the map with a speech bubble. Mornings
// they wave her off to work; afternoons, her ride home, they dance in falling
// confetti. map.js places it at the config's [map.wave] point and redraws it
// with the static overlay (styled in board.css).
import { escapeHtml } from "./format.js";

const NOON = 12;
const LINE_CHARS = 12;      // the bubble wraps at about this many characters
const CHAR_PX = 7.4;        // 13px bold Inter, roughly
const CAP_PX = 9.8;         // its capitals are wider
const LINE_PX = 15;
const CONFETTI = 40;
const CONFETTI_COLORS = ["#ff5a7a", "#ffd23f", "#4fd1c5", "#7aa7ff", "#b98cff", "#ff9f43", "#7ee081"];

// "wave" on a morning ride, "cheer" on an afternoon one (her ride home), else null.
export const waveMode = (ride, now = new Date()) =>
  ride === null || ride === undefined ? null : now.getHours() < NOON ? "wave" : "cheer";

export function bubbleLines(message) {
  const lines = [];
  for (const word of message.split(/\s+/).filter(Boolean)) {
    const last = lines.length - 1;
    if (last >= 0 && lines[last].length + 1 + word.length <= LINE_CHARS) lines[last] += ` ${word}`;
    else lines.push(word);
  }
  return lines;
}

// Ground at y=0, him at x=0, the dog to his right looking up at him. He's in
// a red Nationals jersey (white piping and curly W, short sleeves); the dog's collar is
// night sky with a star and a ringed-planet tag.
const man = (cls, arms) => `<g class="${cls}">` +
  `<path class="jeans" d="M-1.8,-11.5 L-2.4,0 M1.8,-11.5 L2.4,0"/>` +
  `<path class="jersey" d="M-4.2,-11 L-3.6,-20.4 Q0,-21.8 3.6,-20.4 L4.2,-11 Z"/>` +
  `<path class="piping" d="M-1.4,-21 L0,-19.2 L1.4,-21 M0,-19.2 L0,-11.2"/>` +
  `<path class="curly-w" d="M-3,-18.2 Q-2.6,-15.4 -1.9,-14.2 Q-1.3,-15.9 -.9,-17.2 Q-.5,-15.9 .1,-14.2 Q.8,-15.4 1.2,-18.2"` +
  ` transform="translate(1.1,0)"/>` +
  arms +
  `<circle class="face" cx="0" cy="-24.8" r="3.6"/>` +
  `<path class="hair" d="M-3.8,-24.6 C-4.6,-29.8 3.8,-30.6 3.9,-25.4 C2.4,-27.8 -0.8,-27.9 -3,-26.4 Z"/>` +
  `<circle class="eye" cx="-1.3" cy="-24.6" r=".42"/><circle class="eye" cx="1.3" cy="-24.6" r=".42"/>` +
  `<path class="smile" d="M-1,-22.9 Q0,-22.1 1,-22.9"/>` +
  `</g>`;
// An arm from the shoulder (x1, y1) to the hand, its top third in a sleeve;
// one group, so a waving arm swings its sleeve with it.
const arm = (cls, x1, y1, x2, y2) => {
  const sx = x1 + (x2 - x1) * 0.38, sy = y1 + (y2 - y1) * 0.38;
  return `<g class="${cls}"><path class="skin" d="M${x1},${y1} L${x2},${y2}"/>` +
    `<path class="sleeve" d="M${x1},${y1} L${sx.toFixed(2)},${sy.toFixed(2)}"/></g>`;
};
const MAN = man("man",
  arm("still", 3.6, -19.6, 5.6, -12.6) +
  arm("wave", -3.6, -19.6, -7.6, -25.6));   // waving away from the bubble
const DANCER = man("man dance",                               // both arms up, pumping in turn
  arm("arm left", -3.6, -19.6, -7.4, -27.4) +
  arm("arm right", 3.6, -19.6, 7.4, -27.4));
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
  `<circle class="star" cx="9.35" cy="-7.45" r=".28"/>` +
  `<g class="planet"><circle cx="9" cy="-4.9" r=".85"/><ellipse class="ring" cx="9" cy="-4.9" rx="1.5" ry=".42" transform="rotate(-20 9 -4.9)"/></g>` +
  `</g>`;

// A little fluffy white dog with black ears on his other side, facing him, too
// excited to stand still: board.css spins it in circles (the inner group) while
// she rides. Puffs of fur make the body, the head's topknot and the tail.
const puffs = (...cs) => cs.map(([x, y, r]) => `<circle class="fur" cx="${x}" cy="${y}" r="${r}"/>`).join("");
const WHITE_DOG = `<g class="whitedog" transform="translate(-12,0)"><g class="spin">` +
  `<path class="leg" d="M-2.1,-2 L-2.2,0 M-.9,-2 L-.8,0 M1.1,-2 L1,0 M2.3,-2 L2.5,0"/>` +
  `<g class="tail">${puffs([-3.7, -5.4, 1.1], [-4.3, -6.7, .95])}</g>` +
  puffs([-2.3, -3.6, 1.6], [-.7, -4.5, 1.8], [1.1, -4.3, 1.8], [2.3, -3.4, 1.5], [-1.1, -2.8, 1.5], [.9, -2.8, 1.5]) +
  `<path class="ear" d="M4.1,-8.5 Q6,-9.3 6,-7.2 Q5,-7.6 4.1,-8.5 Z"/>` +   // the far ear, peeking
  puffs([3.4, -6.5, 2], [2.4, -8.1, .9], [3.5, -8.6, .95], [4.5, -8.1, .8]) +
  `<ellipse class="fur" cx="5.1" cy="-5.9" rx="1.15" ry=".85"/>` +
  `<circle class="nose" cx="6.15" cy="-6" r=".42"/>` +
  `<path class="collar" d="M1.5,-4.4 L2.2,-6.2"/>` +
  `<path class="ear" d="M3,-8.7 Q.5,-8.8 .7,-5.5 Q1.4,-4.6 2.4,-5.4 Q3.6,-6.8 3,-8.7 Z"/>` +   // floppy, over the collar
  `<circle class="dogeye" cx="4.2" cy="-6.8" r=".36"/>` +
  `</g></g>`;

const f = v => v.toFixed(1);

export const textPx = line => [...line].reduce((px, c) => px + (/[A-Z]/.test(c) ? CAP_PX : CHAR_PX), 0);

// The bubble at his head; (x, y) is the [map.wave] point.
function bubble(x, y, message) {
  const lines = bubbleLines(message);
  const w = Math.max(...lines.map(textPx)) + 20, h = lines.length * LINE_PX + 12;
  const bx = x + 28, by = y + 8;
  const text = lines.map((l, i) => `<tspan x="${f(bx + 10)}" dy="${i ? LINE_PX : 0}">${escapeHtml(l)}</tspan>`).join("");
  return `<path class="bubble" d="M${f(bx + 1)},${f(by + 16)} L${f(x + 12)},${f(y + 32)} L${f(bx + 1)},${f(by + 24)} Z"/>` +
    `<rect class="bubble" x="${f(bx)}" y="${f(by)}" width="${f(w)}" height="${f(h)}" rx="10"/>` +
    `<text x="${f(bx + 10)}" y="${f(by + 19)}">${text}</text>`;
}

// Bits falling over the pair, each already mid-fall (negative delays) so it
// looks like it's been going all along. A fixed seed: every redraw (each pan)
// draws the same confetti.
export function confetti(x, y) {
  let seed = 7;
  const rand = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const out = [];
  for (let i = 0; i < CONFETTI; i++) {
    const px = x - 34 + rand() * 120, py = y - 4 + rand() * 30;
    const w = 4 + rand() * 3, h = 3 + rand() * 4;
    const dur = 2.2 + rand() * 1.6, spin = 0.6 + rand() * 0.8, drift = (rand() - 0.5) * 36;
    out.push(`<g class="confetti" style="--drift:${f(drift)}px;animation-duration:${dur.toFixed(2)}s;animation-delay:-${(rand() * dur).toFixed(2)}s">` +
      `<rect x="${f(px)}" y="${f(py)}" width="${f(w)}" height="${f(h)}" fill="${CONFETTI_COLORS[i % CONFETTI_COLORS.length]}"` +
      ` style="animation-duration:${spin.toFixed(2)}s"/></g>`);
  }
  return out.join("");
}

// They stand just below the point (home is a block from the station dot,
// which would cover them).
// `whiteDog`: the little white dog joins them (kiosk-selector turns it on and off).
const pair = (x, y, man, whiteDog) =>
  `<g transform="translate(${f(x + 2)},${f(y + 92)}) scale(2.4)">${whiteDog ? WHITE_DOG : ""}${man}${DOG}</g>`;

export const waveHtml = (x, y, message, whiteDog = false) =>
  `<g class="wave-home">${pair(x, y, MAN, whiteDog)}${bubble(x, y, message)}</g>`;

export const cheerHtml = (x, y, message, whiteDog = false) =>
  `<g class="wave-home cheer">${pair(x, y, DANCER, whiteDog)}${confetti(x, y)}${bubble(x, y, message)}</g>`;

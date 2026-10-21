"""Draw the phone page's home-screen icon: a tiny departure board (three
line-coloured dots with bars) on the board's near-black.

Dev-only (needs Pillow, which the app doesn't). Re-run after changing the
design, then commit the PNGs:

    python tools/render_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "web" / "icons"
SIZES = {"icon-180.png": 180, "icon-192.png": 192, "icon-512.png": 512, "favicon-32.png": 32}
BG = "#0d1117"
ROWS = [("#ed8b00", 0.78), ("#919d9d", 0.62), ("#c80f2d", 0.70)]   # OR, SV, RD; bar lengths
SS = 4   # supersampling


def draw(size: int) -> Image.Image:
    n = size * SS
    img = Image.new("RGB", (n, n), BG)
    d = ImageDraw.Draw(img)
    # Everything sits inside the central ~64% so Android's maskable crop keeps it.
    left, top, span = 0.245 * n, 0.25 * n, 0.50 * n
    r = 0.075 * n
    for i, (color, length) in enumerate(ROWS):
        cy = top + i * span / 2
        d.ellipse([left, cy - r, left + 2 * r, cy + r], fill=color)
        x0, x1 = left + 2.7 * r, left + 2.7 * r + length * (0.60 * n - 2.7 * r)
        h = 0.36 * r
        d.rounded_rectangle([x0, cy - h, x1, cy + h], radius=h, fill="#e6ebf1" if i == 0 else "#5d6875")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, size in SIZES.items():
        draw(size).save(OUT / name, optimize=True)
        print("wrote", OUT / name)

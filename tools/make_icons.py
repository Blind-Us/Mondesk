"""Draws the Mondesk icon. One list of shapes is the only source: it becomes the SVG the pages use, the
PNGs of the browser extension, and the .ico / .png of the application.

Two versions of the same picture:
  app        the little cream computer by itself (transparent around it): the application
  extension  the same on a dark rounded tile: the browser extension

Run:  python tools/make_icons.py     (needs Pillow; the results are committed, so users never run it)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CREAM, DARK, AMBER = "#f1ead9", "#1b1b22", "#e9b66b"

# (x, y, width, height, corner radius, colour, opacity) on a 256 x 256 field
COMPUTER = [
    (36, 46, 184, 138, 32, CREAM, 1),      # body
    (52, 62, 152, 106, 20, DARK, 1),       # screen
    (64, 74, 50, 82, 12, AMBER, 1),        # one amber module
    (124, 74, 68, 36, 12, CREAM, 1),       # two white ones
    (124, 120, 68, 36, 12, CREAM, .45),
    (82, 198, 92, 14, 7, CREAM, 1),        # base: a thin foot
]
TILE = [(0, 0, 256, 256, 58, DARK, 1)]
# without the tile the computer may fill more of the picture
APP_SCALE, APP_SHIFT = 1.2, (-25.6, -30)


def shapes(kind):
    if kind == "extension":
        return TILE + COMPUTER
    s, (dx, dy) = APP_SCALE, APP_SHIFT
    return [(x * s + dx, y * s + dy, w * s, h * s, r * s, c, o) for x, y, w, h, r, c, o in COMPUTER]


def svg(kind):
    rows = "\n".join(f'  <rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{r:g}" fill="{c}"' + (f' opacity="{o:g}"' if o < 1 else "") + "/>"
                     for x, y, w, h, r, c, o in shapes(kind))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">\n  <!-- drawn by tools/make_icons.py -->\n{rows}\n</svg>\n'


def png(kind, size):
    from PIL import Image, ImageDraw
    over = 8 if size <= 64 else 4                      # draw large, then shrink: smooth edges
    big = size * over
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    k = big / 256
    for x, y, w, h, r, c, o in shapes(kind):
        layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        rgb = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        ImageDraw.Draw(layer).rounded_rectangle([x * k, y * k, (x + w) * k, (y + h) * k], radius=r * k, fill=rgb + (round(255 * o),))
        image = Image.alpha_composite(image, layer)
    return image.resize((size, size), Image.LANCZOS)


def build():
    out = []
    web, ext, assets = ROOT / "web", ROOT / "apple-music-extension" / "icons", ROOT / "assets"
    ext.mkdir(exist_ok=True); assets.mkdir(exist_ok=True)
    (web / "icon.svg").write_text(svg("app"), encoding="utf-8"); out.append(web / "icon.svg")
    (assets / "mondesk-extension.svg").write_text(svg("extension"), encoding="utf-8"); out.append(assets / "mondesk-extension.svg")
    for size in (16, 32, 48, 128):
        png("extension", size).save(ext / f"icon{size}.png"); out.append(ext / f"icon{size}.png")
    png("app", 512).save(assets / "mondesk.png"); out.append(assets / "mondesk.png")
    png("app", 256).save(web / "icon.png"); out.append(web / "icon.png")
    # Windows: every size drawn on its own (not one picture shrunk by Windows)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [png("app", s) for s in sizes]
    frames[-1].save(assets / "mondesk.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    out.append(assets / "mondesk.ico")
    return out


if __name__ == "__main__":
    for path in build():
        print(path.relative_to(ROOT))

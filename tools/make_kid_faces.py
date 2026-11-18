"""Draws the built-in "耳機小子" character pack (web/companion/kid/*.svg).

Every face shares the same head, hair, headphones and hoodie; only the eyes, brows, mouth
and a small extra (sweat drop, Zzz…) change, so switching faces never makes the head jump.
talk_open / talk_closed differ only in the mouth, as CHARACTER-FORMAT.md recommends.

    python tools/make_kid_faces.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "companion" / "kid"

INK = "#3a2833"        # outlines and facial lines
SKIN, SKIN_SHADE = "#ffe3cc", "#f5c9a8"
HAIR, HAIR_LIGHT = "#2e3456", "#465082"
HOODIE, HOODIE_SHADE = "#6c7cf5", "#5363d8"
CUP, CUP_LIGHT = "#ff7a5c", "#ffa58b"
BAND, PAD = "#8e97c4", "#3b4060"
IRIS_TOP, IRIS_BOTTOM = "#2c2547", "#5f7dff"
MOUTH, TONGUE = "#8c2f45", "#ff8c96"

DEFS = f"""<defs>
  <linearGradient id="iris" x1="0" y1="0" x2="0" y2="1"><stop offset=".35" stop-color="{IRIS_TOP}"/><stop offset="1" stop-color="{IRIS_BOTTOM}"/></linearGradient>
  <linearGradient id="cup" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{CUP_LIGHT}"/><stop offset="1" stop-color="{CUP}"/></linearGradient>
  <radialGradient id="blush"><stop offset="0" stop-color="#ff8a9a" stop-opacity=".55"/><stop offset="1" stop-color="#ff8a9a" stop-opacity="0"/></radialGradient>
</defs>"""

# shoulders + hoodie, neck, back hair, head, headphones, bangs — drawn back to front
BASE = f"""
<path d="M96 512 C100 452 150 420 210 412 L302 412 C362 420 412 452 416 512 Z" fill="{HOODIE}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<path d="M196 414 C214 452 298 452 316 414" fill="{HOODIE_SHADE}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<path d="M226 404 L226 432 Q256 446 286 432 L286 404 Z" fill="{SKIN_SHADE}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<path d="M168 450 Q160 480 166 512 M344 450 Q352 480 346 512" fill="none" stroke="{HOODIE_SHADE}" stroke-width="8" stroke-linecap="round"/>
<circle cx="166" cy="488" r="7" fill="#e9ecff"/><circle cx="346" cy="488" r="7" fill="#e9ecff"/>
<path d="M98 270 C88 150 168 74 256 74 C344 74 424 150 414 270 C410 330 392 360 372 372 L140 372 C120 360 102 330 98 270 Z" fill="{HAIR}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<path d="M122 262 C122 170 180 118 256 118 C332 118 390 170 390 262 C390 352 334 410 256 410 C178 410 122 352 122 262 Z" fill="{SKIN}" stroke="{INK}" stroke-width="6"/>
<path d="M150 372 C178 400 214 412 256 412 C298 412 334 400 362 372 C330 396 296 404 256 404 C216 404 182 396 150 372 Z" fill="{SKIN_SHADE}"/>
<ellipse cx="176" cy="334" rx="34" ry="20" fill="url(#blush)"/>
<ellipse cx="336" cy="334" rx="34" ry="20" fill="url(#blush)"/>
<path d="M128 236 C132 150 190 104 256 104 C322 104 380 150 384 236 C368 214 352 200 336 194 C338 210 334 222 326 232 C312 210 292 194 268 186 C270 204 262 218 250 228 C244 208 230 196 210 190 C206 208 194 222 176 230 C178 214 174 202 166 194 C150 206 138 220 128 236 Z" fill="{HAIR}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<path d="M184 134 C206 120 236 114 262 116" fill="none" stroke="{HAIR_LIGHT}" stroke-width="10" stroke-linecap="round"/>
<path d="M96 262 C90 112 170 50 256 50 C342 50 422 112 416 262" fill="none" stroke="{INK}" stroke-width="30" stroke-linecap="round"/>
<path d="M96 262 C90 112 170 50 256 50 C342 50 422 112 416 262" fill="none" stroke="{BAND}" stroke-width="18" stroke-linecap="round"/>
<path d="M150 98 C184 70 220 58 256 58" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="5" stroke-linecap="round"/>
<path d="M262 66 C252 36 266 12 296 10 C282 24 278 42 284 62" fill="{HAIR}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>
<rect x="104" y="214" width="34" height="120" rx="16" fill="{PAD}" stroke="{INK}" stroke-width="6"/>
<rect x="374" y="214" width="34" height="120" rx="16" fill="{PAD}" stroke="{INK}" stroke-width="6"/>
<rect x="58" y="206" width="58" height="136" rx="28" fill="url(#cup)" stroke="{INK}" stroke-width="6"/>
<rect x="396" y="206" width="58" height="136" rx="28" fill="url(#cup)" stroke="{INK}" stroke-width="6"/>
<path d="M76 234 Q72 270 76 306" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="7" stroke-linecap="round"/>
<path d="M414 234 Q410 270 414 306" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="7" stroke-linecap="round"/>
<circle cx="87" cy="320" r="5" fill="#fff6c8"/>
"""


def eye(cx, cy, dx=0, dy=0, scale=1.0):
    """Open eye: dark oval, blue-bottom iris, two highlights; dx/dy move the gaze."""
    rx, ry = 21 * scale, 28 * scale
    return (f'<ellipse cx="{cx}" cy="{cy}" rx="{rx:.1f}" ry="{ry:.1f}" fill="url(#iris)" stroke="{INK}" stroke-width="4"/>'
            f'<circle cx="{cx - 7 + dx}" cy="{cy - 10 + dy}" r="{8 * scale:.1f}" fill="#fff"/>'
            f'<circle cx="{cx + 7 + dx}" cy="{cy + 10 + dy}" r="{3.5 * scale:.1f}" fill="#fff" opacity=".85"/>')


def line(d, w=7):
    return f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


EYES_OPEN = eye(200, 288) + eye(312, 288)
BROWS_CALM = line("M176 246 Q198 238 220 244", 6) + line("M292 244 Q314 238 336 246", 6)
SMILE = line("M236 344 Q256 360 276 344")
OPEN_MOUTH = (f'<path d="M232 340 Q256 336 280 340 Q278 378 256 380 Q234 378 232 340 Z" fill="{MOUTH}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
              f'<path d="M240 368 Q256 358 272 368 Q266 378 256 378 Q246 378 240 368 Z" fill="{TONGUE}"/>')

FACES = {
    "neutral": EYES_OPEN + BROWS_CALM + SMILE,
    "talk_closed": EYES_OPEN + BROWS_CALM + SMILE,
    "talk_open": EYES_OPEN + BROWS_CALM + OPEN_MOUTH,
    "happy": (
        line("M178 296 Q200 268 222 296", 8) + line("M290 296 Q312 268 334 296", 8)
        + line("M176 238 Q198 226 220 234", 6) + line("M292 234 Q314 226 336 238", 6)
        + f'<path d="M222 334 Q256 342 290 334 Q286 388 256 390 Q226 388 222 334 Z" fill="{MOUTH}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>'
        + f'<path d="M236 374 Q256 360 276 374 Q268 388 256 389 Q244 388 236 374 Z" fill="{TONGUE}"/>'
        + '<ellipse cx="176" cy="334" rx="30" ry="16" fill="#ff8a9a" opacity=".35"/><ellipse cx="336" cy="334" rx="30" ry="16" fill="#ff8a9a" opacity=".35"/>'
        + '<path d="M448 150 l8 20 20 8 -20 8 -8 20 -8 -20 -20 -8 20 -8 Z" fill="#ffd45c" stroke="#3a2833" stroke-width="4" stroke-linejoin="round"/>'
        + '<path d="M60 128 l5 12 12 5 -12 5 -5 12 -5 -12 -12 -5 12 -5 Z" fill="#ffd45c" stroke="#3a2833" stroke-width="3" stroke-linejoin="round"/>'
    ),
    "thinking": (
        eye(200, 288, dx=8, dy=-8) + eye(312, 288, dx=8, dy=-8)
        + line("M176 248 Q198 242 220 248", 6) + line("M292 234 Q314 220 336 230", 6)
        + line("M240 352 Q254 344 272 350")
        + f'<circle cx="420" cy="158" r="9" fill="#e9ecff" stroke="{INK}" stroke-width="4"/>'
        + f'<circle cx="446" cy="122" r="13" fill="#e9ecff" stroke="{INK}" stroke-width="4"/>'
        + f'<ellipse cx="452" cy="72" rx="36" ry="26" fill="#e9ecff" stroke="{INK}" stroke-width="4"/>'
        + f'<circle cx="438" cy="72" r="4" fill="{INK}"/><circle cx="452" cy="72" r="4" fill="{INK}"/><circle cx="466" cy="72" r="4" fill="{INK}"/>'
    ),
    "worried": (
        eye(200, 292, dy=4, scale=.92) + eye(312, 292, dy=4, scale=.92)
        + line("M178 246 Q200 244 220 232", 6) + line("M292 232 Q312 244 334 246", 6)
        + line("M234 356 Q245 346 256 354 Q267 362 278 352", 6)
        + f'<path d="M378 168 Q394 196 394 208 A16 16 0 0 1 362 208 Q362 196 378 168 Z" fill="#9fd4ff" stroke="{INK}" stroke-width="4" stroke-linejoin="round"/>'
        + '<path d="M372 204 Q372 212 378 214" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round"/>'
    ),
    "surprised": (
        f'<circle cx="200" cy="288" r="27" fill="#fff" stroke="{INK}" stroke-width="5"/><circle cx="200" cy="290" r="13" fill="url(#iris)"/><circle cx="196" cy="285" r="4.5" fill="#fff"/>'
        f'<circle cx="312" cy="288" r="27" fill="#fff" stroke="{INK}" stroke-width="5"/><circle cx="312" cy="290" r="13" fill="url(#iris)"/><circle cx="308" cy="285" r="4.5" fill="#fff"/>'
        + line("M174 236 Q198 220 222 230", 6) + line("M290 230 Q314 220 338 236", 6)
        + f'<ellipse cx="256" cy="358" rx="16" ry="20" fill="{MOUTH}" stroke="{INK}" stroke-width="5"/>'
        + f'<path d="M452 110 L444 168" stroke="{INK}" stroke-width="18" stroke-linecap="round"/><path d="M452 110 L444 168" stroke="#ffd45c" stroke-width="9" stroke-linecap="round"/><circle cx="441" cy="194" r="10" fill="#ffd45c" stroke="{INK}" stroke-width="4"/>'
    ),
    "sleepy": (
        line("M180 294 Q200 306 220 294", 7) + line("M292 294 Q312 306 332 294", 7)
        + line("M178 256 Q198 252 220 258", 6) + line("M292 258 Q314 252 334 256", 6)
        + f'<ellipse cx="256" cy="358" rx="13" ry="11" fill="{MOUTH}" stroke="{INK}" stroke-width="4"/>'
       
        + f'<text x="404" y="140" font-family="Arial Rounded MT Bold, Arial, sans-serif" font-weight="700" font-size="58" fill="#c9d3ff" stroke="{INK}" stroke-width="3" paint-order="stroke">Z</text>'
        + f'<text x="448" y="92" font-family="Arial Rounded MT Bold, Arial, sans-serif" font-weight="700" font-size="40" fill="#c9d3ff" stroke="{INK}" stroke-width="3" paint-order="stroke">z</text>'
    ),
}


def svg(name, face):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
            f'<!-- Mondesk Companion built-in character "耳機小子": {name}. Made by tools/make_kid_faces.py -->\n'
            f'{DEFS}{BASE}{face}\n</svg>\n')


if __name__ == "__main__":
    for name, face in FACES.items():
        (OUT / f"{name}.svg").write_text(svg(name, face), encoding="utf-8", newline="\n")
    print(f"wrote {len(FACES)} faces to {OUT}")

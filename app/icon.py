"""Programmatic icon: a tower being dismantled, for 极简卸载.

Concept — "拆楼": a white tower whose upper-right corner has been broken away
along a staircase edge, with the removed blocks tumbling off to the upper right.
The metaphor matches what the app does (take an app apart, piece by piece) and
stays readable down to 16 px because it is one bold silhouette plus two blocks.

Rendered at 4x supersampling and downsampled with LANCZOS.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BG_TOP = (10, 132, 255)      # Apple system blue
BG_MID = (0, 108, 235)
BG_BOT = (0, 68, 176)
WHITE = (255, 255, 255)
# Window openings read as glass: the background colour, slightly darkened.
GLASS = (0, 58, 150)


def _lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _squircle(size: int, radius_ratio: float = 0.225) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=int(size * radius_ratio), fill=255)
    return m


def _gradient(size: int) -> Image.Image:
    g = Image.new("RGB", (1, size))
    d = ImageDraw.Draw(g)
    for y in range(size):
        t = y / max(1, size - 1)
        d.point((0, y), _lerp(BG_TOP, BG_MID, t / 0.55) if t < 0.55
                else _lerp(BG_MID, BG_BOT, (t - 0.55) / 0.45))
    return g.resize((size, size))


def _rotated_block(size: int, box, angle: float, alpha: int) -> Image.Image:
    """A rounded square drawn on its own canvas, rotated about its centre."""
    x0, y0, x1, y1 = box
    w = int((x1 - x0) * 1.9)
    canvas = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    inset = int(w * 0.24)
    d.rounded_rectangle([inset, inset, w - inset, w - inset],
                        radius=int(w * 0.10), fill=WHITE + (alpha,))
    canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=False)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(canvas, (int((x0 + x1) / 2 - w / 2), int((y0 + y1) / 2 - w / 2)), canvas)
    return out


def render(size: int = 256) -> Image.Image:
    S = size * 4
    # Small raster sizes cannot hold windows plus debris; keep the silhouette
    # bold and drop the smallest details instead of producing grey mush.
    small = size <= 32
    tiny = size <= 20
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # 1. squircle body
    mask = _squircle(S)
    body = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    body.paste(_gradient(S), (0, 0), mask)
    img.alpha_composite(body)

    # 2. soft top highlight for depth
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([-S * 0.30, -S * 0.62, S * 0.95, S * 0.42],
                               fill=(255, 255, 255, 44))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 0.055))
    hl.putalpha(Image.composite(hl.split()[3], Image.new("L", (S, S), 0), mask))
    img.alpha_composite(hl)

    # 3. tower: rounded rectangle, upper-right corner already gone
    bx0, by0 = int(S * 0.185), int(S * 0.275)
    bx1, by1 = int(S * 0.645), int(S * 0.815)
    tower = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(tower).rounded_rectangle([bx0, by0, bx1, by1],
                                            radius=int(S * 0.050),
                                            fill=WHITE + (252,))
    # staircase break: remove a stepped wedge from the top-right
    step_x = (0.430, 0.538, 0.645)
    step_y = (0.275, 0.395, 0.520)
    cut = Image.new("L", (S, S), 0)
    ImageDraw.Draw(cut).polygon(
        [(int(S * step_x[0]), by0 - int(S * 0.02)),
         (bx1 + int(S * 0.02), by0 - int(S * 0.02)),
         (bx1 + int(S * 0.02), by1 + int(S * 0.02)),
         (int(S * step_x[2]), by1 + int(S * 0.02)),
         (int(S * step_x[2]), int(S * step_y[2])),
         (int(S * step_x[1]), int(S * step_y[2])),
         (int(S * step_x[1]), int(S * step_y[1])),
         (int(S * step_x[0]), int(S * step_y[1]))],
        fill=255)
    tower.putalpha(Image.composite(Image.new("L", (S, S), 0), tower.split()[3], cut))
    img.alpha_composite(tower)

    # 4. windows, skipped where the tower was cut away
    wd = ImageDraw.Draw(img)
    cols = 2 if small else 3
    rows = 3 if small else 4
    win = int(S * (0.062 if small else 0.050))
    gap = int(S * (0.088 if small else 0.072))
    for row in range(rows):
        wy = int(S * (0.360 if small else 0.380)) + row * gap
        for col in range(cols):
            wx = int(S * (0.255 if small else 0.250)) + col * gap
            if wx + win > bx1 - int(S * 0.040):
                continue
            if wy > int(S * step_y[2]):
                limit = int(S * step_x[2]) - int(S * 0.012)
            elif wy > int(S * step_y[1]):
                limit = int(S * step_x[1]) - int(S * 0.012)
            else:
                limit = int(S * step_x[0]) - int(S * 0.012)
            if wx + win > limit:
                continue
            wd.rounded_rectangle([wx, wy, wx + win, wy + win],
                                 radius=int(win * 0.26), fill=GLASS + (135,))

    # 5. the removed blocks, drifting up and right
    if tiny:
        img.alpha_composite(_rotated_block(S, (S * 0.600, S * 0.235, S * 0.800, S * 0.435), -12, 252))
    elif small:
        img.alpha_composite(_rotated_block(S, (S * 0.590, S * 0.250, S * 0.775, S * 0.435), -12, 252))
        img.alpha_composite(_rotated_block(S, (S * 0.745, S * 0.130, S * 0.870, S * 0.255), 22, 205))
    else:
        img.alpha_composite(_rotated_block(S, (S * 0.585, S * 0.255, S * 0.760, S * 0.430), -13, 252))
        img.alpha_composite(_rotated_block(S, (S * 0.755, S * 0.130, S * 0.875, S * 0.250), 22, 205))
        # small debris only where there are enough pixels to read it
        for cx, cy, r, a in ((0.700, 0.505, 0.017, 150), (0.762, 0.585, 0.012, 118),
                             (0.655, 0.620, 0.010, 100)):
            wd.rounded_rectangle([int(S * (cx - r)), int(S * (cy - r)),
                                  int(S * (cx + r)), int(S * (cy + r))],
                                 radius=int(S * 0.007), fill=WHITE + (a,))

    # 6. rim light
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([1, 1, S - 2, S - 2],
                                          radius=int(S * 0.225),
                                          outline=(255, 255, 255, 62),
                                          width=max(1, S // 128))
    rim.putalpha(Image.composite(rim.split()[3], Image.new("L", (S, S), 0), mask))
    img.alpha_composite(rim)

    return img.resize((size, size), Image.LANCZOS)


def save_ico(path: Path, sizes=(16, 20, 24, 32, 40, 48, 64, 96, 128, 256)) -> Path:
    base = render(256)
    imgs = [render(s) for s in sizes]
    path.parent.mkdir(parents=True, exist_ok=True)
    base.save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs)
    return path


def save_png(path: Path, size: int = 512) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    render(size).save(path, format="PNG")
    return path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    save_ico(here / "assets" / "jijian.ico")
    save_png(here / "assets" / "jijian_512.png")
    save_png(here / "assets" / "jijian_128.png", 128)
    print("icons written")

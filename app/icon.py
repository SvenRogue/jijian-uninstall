"""Programmatic icon: a rounded "shard" glyph for 极简卸载.

Concept: a tilted rounded square (app) whose lower-right corner is being
lifted away, with a small downward arrow carved in the accent colour.
Rendered at 4x supersampling and downsized for smooth edges on every size.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ACCENT_A = (140, 163, 255)
ACCENT_B = (90, 120, 240)
ACCENT_DEEP = (58, 78, 190)
WHITE = (255, 255, 255)
REMOVE = (255, 96, 112)


def _lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def render(size: int = 256) -> Image.Image:
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # ---- 1. rounded squircle background with diagonal gradient
    grad = Image.new("RGB", (1, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.point((0, y), _lerp(ACCENT_A, ACCENT_DEEP, y / (S - 1)))
    grad = grad.resize((S, S))
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg.paste(grad, (0, 0), _rounded_mask(S, int(S * 0.235)))
    img.alpha_composite(bg)

    # ---- 2. soft inner highlight at the top-left
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hd.ellipse([-S * 0.35, -S * 0.55, S * 0.85, S * 0.45], fill=(255, 255, 255, 46))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 0.06))
    hl.putalpha(Image.composite(hl.split()[3], Image.new("L", (S, S), 0), _rounded_mask(S, int(S * 0.235))))
    img.alpha_composite(hl)

    # ---- 3. white shard body: rounded square, lower-right corner cut
    shard = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shard)
    L = int(S * 0.205)
    W = int(S * 0.59)
    R = int(S * 0.115)
    x0, y0 = L, int(S * 0.245)
    x1, y1 = L + W, int(S * 0.245) + W
    # body
    sd.rounded_rectangle([x0, y0, x1, y1], radius=R, fill=(255, 255, 255, 246))
    shard.alpha_composite(shard)

    # cut the lower-right corner off (the "removed" piece)
    cut = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cut)
    cx = x1 - int(W * 0.46)
    cy = y1 - int(W * 0.46)
    cd.polygon([(x1 + 2, cy - int(S * 0.02)), (x1 + 2, y1 + 2), (cx - int(S * 0.02), y1 + 2)],
               fill=(0, 0, 0, 255))
    # make the cut edge follow the rounded corner slightly
    cd.ellipse([cx - R * 1.4, cy - R * 1.4, cx + R * 1.4, cy + R * 1.4], fill=(0, 0, 0, 0))
    body_alpha = shard.split()[3]
    cut_alpha = cut.split()[3]
    new_alpha = Image.composite(Image.new("L", (S, S), 0), body_alpha, cut_alpha)
    shard.putalpha(new_alpha)
    img.alpha_composite(shard)

    # ---- 4. the detached piece drifting away (small rotated square, faded)
    piece = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pd = ImageDraw.Draw(piece)
    ps = int(W * 0.30)
    ox, oy = x1 - int(W * 0.05), y1 - int(W * 0.05)
    pd.rounded_rectangle([ox - ps // 2, oy - ps // 2, ox + ps // 2, oy + ps // 2],
                         radius=int(ps * 0.28), fill=(255, 255, 255, 120))
    piece = piece.rotate(-18, resample=Image.BICUBIC, center=(ox, oy))
    img.alpha_composite(piece)

    # ---- 5. down-arrow carved through the shard (accent colour)
    arrow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arrow)
    cxm = (x0 + x1) / 2 - S * 0.035
    top = y0 + W * 0.20
    bot = y0 + W * 0.62
    stem_w = int(S * 0.055)
    head_w = int(S * 0.145)
    ad.rounded_rectangle([cxm - stem_w // 2, top, cxm + stem_w // 2, bot - head_w * 0.35],
                         radius=stem_w // 2, fill=ACCENT_DEEP + (255,))
    ad.polygon([(cxm - head_w // 2, bot - head_w * 0.62),
                (cxm + head_w // 2, bot - head_w * 0.62),
                (cxm, bot)], fill=ACCENT_DEEP + (255,))
    img.alpha_composite(arrow)

    # ---- 6. subtle rim light
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    rd.rounded_rectangle([1, 1, S - 2, S - 2], radius=int(S * 0.235),
                         outline=(255, 255, 255, 64), width=max(1, S // 128))
    rim.putalpha(Image.composite(rim.split()[3], Image.new("L", (S, S), 0), _rounded_mask(S, int(S * 0.235))))
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

#!/usr/bin/env python3
"""Genera los assets de LiveArea de VitaMon (PNG 8-bit indexados, como exige la Vita).

    pip install pillow && python tools/make_assets.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vita", "sce_sys")
BG = (0x10, 0x14, 0x18)
PANEL = (0x1B, 0x21, 0x28)
GREEN = (0x3C, 0xC8, 0x6E)
AMBER = (0xF0, 0xB4, 0x28)
RED = (0xE8, 0x48, 0x48)
TEXT = (0xE6, 0xEA, 0xEE)

TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<livearea style="a1" format-ver="01.00" content-rev="1">
  <livearea-background>
    <image>bg.png</image>
  </livearea-background>
  <gate>
    <startup-image>startup.png</startup-image>
  </gate>
</livearea>
"""


def font(size):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def bars(d, x, y, w, h, n=5):
    """Mini gráfico de barras: el motivo del ícono."""
    heights = [0.35, 0.6, 0.45, 0.85, 0.7][:n]
    colors = [GREEN, GREEN, GREEN, RED, AMBER][:n]
    gap = w // (n * 4)
    bw = (w - gap * (n - 1)) // n
    for i, (f, c) in enumerate(zip(heights, colors)):
        bx = x + i * (bw + gap)
        d.rectangle([bx, y + h - int(h * f), bx + bw - 1, y + h - 1], fill=c)


def save(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").quantize(colors=256).save(path, optimize=True)
    assert Image.open(path).mode == "P", path  # la Vita rechaza PNG que no sean indexados
    print("ok", os.path.relpath(path))


def icon():
    img = Image.new("RGB", (128, 128), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, 119, 119], radius=16, fill=PANEL)
    bars(d, 22, 26, 84, 62)
    d.text((64, 104), "VitaMon", fill=TEXT, font=font(16), anchor="mm")
    save(img, os.path.join(OUT, "icon0.png"))


def bg():
    img = Image.new("RGB", (840, 500), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, 799, 459], radius=24, fill=PANEL)
    bars(d, 90, 120, 300, 240)
    d.text((440, 200), "VitaMon", fill=TEXT, font=font(64), anchor="lm")
    d.text((444, 270), "Monitor de PC", fill=(0x8A, 0x94, 0x9E), font=font(30), anchor="lm")
    save(img, os.path.join(OUT, "livearea", "contents", "bg.png"))


def startup():
    img = Image.new("RGB", (280, 158), PANEL)
    d = ImageDraw.Draw(img)
    bars(d, 24, 34, 90, 90)
    d.text((132, 79), "VitaMon", fill=TEXT, font=font(30), anchor="lm")
    save(img, os.path.join(OUT, "livearea", "contents", "startup.png"))


if __name__ == "__main__":
    icon()
    bg()
    startup()
    with open(os.path.join(OUT, "livearea", "contents", "template.xml"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    print("ok template.xml")

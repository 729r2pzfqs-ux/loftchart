#!/usr/bin/env python3
"""Rasterise LoftChart's favicon SVG into the PNG/ICO variants plus the OG image."""

import io
import os

import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
SVG = os.path.join(STATIC, "favicon.svg")

GREEN = (27, 67, 50)
GOLD = (201, 169, 78)
OFFWHITE = (250, 250, 247)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]


def font(size, bold=True):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render(size):
    png = cairosvg.svg2png(url=SVG, output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def centered(draw, text, fnt, cx, y, fill):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    draw.text((cx - (right - left) / 2 - left, y), text, font=fnt, fill=fill)
    return bottom - top


def main():
    # apple-touch-icon: flatten onto the brand green (iOS ignores alpha)
    icon180 = render(180)
    flat = Image.new("RGB", (180, 180), GREEN)
    flat.paste(icon180, (0, 0), icon180)
    flat.save(os.path.join(STATIC, "apple-touch-icon.png"))

    render(192).save(os.path.join(STATIC, "favicon-192.png"))
    render(512).save(os.path.join(STATIC, "favicon-512.png"))
    render(32).save(os.path.join(STATIC, "favicon-32x32.png"))
    render(16).save(os.path.join(STATIC, "favicon-16x16.png"))

    ico = render(64)
    ico.save(os.path.join(STATIC, "favicon.ico"),
             sizes=[(16, 16), (32, 32), (48, 48)])

    # ---- Open Graph card ----
    W, H = 1200, 630
    og = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(og)

    # subtle vignette panel + gold rule
    d.rectangle([0, 0, W, 8], fill=GOLD)
    d.rectangle([0, H - 8, W, H], fill=GOLD)

    logo = render(148)
    og.paste(logo, ((W - 148) // 2, 116), logo)

    centered(d, "LoftChart.com", font(84), W / 2, 300, OFFWHITE)
    centered(d, "Golf Club Specifications Database", font(40), W / 2, 408, GOLD)
    centered(d, "Every club.  Every spec.  Every generation.",
             font(28), W / 2, 486, (168, 190, 176))

    og.save(os.path.join(STATIC, "og-default.png"), optimize=True)
    print("assets written to", STATIC)


if __name__ == "__main__":
    main()

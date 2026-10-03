#!/usr/bin/env python3
"""Render the PWA and Android launcher icons from one vector-ish drawing."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ICONS = ROOT / "public" / "icons"
ANDROID_RES = ROOT / "android" / "app" / "src" / "main" / "res"

TOP = (16, 150, 122)
BOTTOM = (9, 92, 78)
LIQUID = (245, 176, 92)
LIQUID_DEEP = (231, 143, 62)
WHITE = (255, 255, 255)

MASTER = 1024


def gradient_square(size: int, radius: int) -> Image.Image:
    base = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(base)
    for y in range(size):
        ratio = y / (size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * ratio) for i in range(3)),
        )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(base, (0, 0), mask)
    return rounded


FLASK = [
    (452, 268),
    (572, 268),
    (572, 428),
    (716, 726),
    (700, 772),
    (324, 772),
    (308, 726),
    (452, 428),
]


def draw_flask(size: int, scale: float = 1.0, offset: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    centre = size / 2
    points = [
        (
            centre + (x - MASTER / 2) * scale + offset[0],
            centre + (y - MASTER / 2) * scale + offset[1],
        )
        for x, y in FLASK
    ]
    flask_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(flask_mask).polygon(points, fill=255)

    draw = ImageDraw.Draw(layer)
    draw.polygon(points, fill=WHITE)

    liquid = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    liquid_draw = ImageDraw.Draw(liquid)
    liquid_top = centre + (560 - MASTER / 2) * scale
    liquid_draw.rectangle(
        [0, liquid_top, size, size],
        fill=LIQUID + (255,),
    )
    liquid_draw.ellipse(
        [
            centre + (330 - MASTER / 2) * scale,
            liquid_top - 26 * scale,
            centre + (694 - MASTER / 2) * scale,
            liquid_top + 40 * scale,
        ],
        fill=LIQUID_DEEP + (255,),
    )
    layer.paste(liquid, (0, 0), Image.composite(flask_mask, Image.new("L", (size, size), 0), liquid.getchannel("A")))

    bubbles = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bubble_draw = ImageDraw.Draw(bubbles)
    for cx, cy, r in ((448, 690, 26), (556, 660, 15), (500, 728, 11)):
        bubble_draw.ellipse(
            [
                centre + (cx - MASTER / 2 - r) * scale,
                centre + (cy - MASTER / 2 - r) * scale,
                centre + (cx - MASTER / 2 + r) * scale,
                centre + (cy - MASTER / 2 + r) * scale,
            ],
            fill=(255, 255, 255, 190),
        )
    layer.alpha_composite(Image.composite(bubbles, Image.new("RGBA", (size, size), (0, 0, 0, 0)), flask_mask))

    rim = Image.new("L", (size, size), 0)
    ImageDraw.Draw(rim).rounded_rectangle(
        [
            centre + (438 - MASTER / 2) * scale,
            centre + (252 - MASTER / 2) * scale,
            centre + (586 - MASTER / 2) * scale,
            centre + (300 - MASTER / 2) * scale,
        ],
        radius=22 * scale,
        fill=255,
    )
    layer.paste((255, 255, 255, 255), (0, 0), rim)
    return layer


def draw_molecule(size: int, scale: float = 1.0) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    centre = size / 2
    nodes = [(736, 300), (824, 236), (830, 356)]

    def point(x: float, y: float) -> tuple[float, float]:
        return (
            centre + (x - MASTER / 2) * scale,
            centre + (y - MASTER / 2) * scale,
        )

    for start, end in ((0, 1), (0, 2)):
        draw.line([point(*nodes[start]), point(*nodes[end])], fill=(255, 255, 255, 205), width=round(20 * scale))
    for index, (x, y) in enumerate(nodes):
        radius = (34 if index == 0 else 26) * scale
        px, py = point(x, y)
        draw.ellipse([px - radius, py - radius, px + radius, py + radius], fill=(255, 255, 255, 235))
    return layer


def master_icon() -> Image.Image:
    canvas = gradient_square(MASTER, radius=228)
    canvas.alpha_composite(draw_molecule(MASTER, 0.86))
    canvas.alpha_composite(draw_flask(MASTER, 1.12, (0.0, 34.0)))
    return canvas


def adaptive_foreground() -> Image.Image:
    layer = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    layer.alpha_composite(draw_molecule(MASTER, 0.56))
    layer.alpha_composite(draw_flask(MASTER, 0.68, (0.0, 34.0)))
    return layer


def save(image: Image.Image, path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((size, size), Image.LANCZOS).save(path)


def main() -> None:
    icon = master_icon()
    foreground = adaptive_foreground()

    save(icon, PUBLIC_ICONS / "icon-512.png", 512)
    save(icon, PUBLIC_ICONS / "icon-192.png", 192)
    save(icon, PUBLIC_ICONS / "apple-touch-icon.png", 180)

    densities = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for density, size in densities.items():
        folder = ANDROID_RES / f"mipmap-{density}"
        save(icon, folder / "ic_launcher.png", size)
        save(icon, folder / "ic_launcher_round.png", size)
        save(foreground, folder / "ic_launcher_foreground.png", size)
    print("icons written")


if __name__ == "__main__":
    main()

"""
Extract individual layer PNGs from rower_sheet_long.png.

The source file uses a gray checkerboard fill (RGB, no alpha) to mark
background/separator regions. Content bands are detected by measuring the
fraction of "neutral gray" pixels per row.

The water layer shares its horizontal band with small rower-frame previews on
the right, so we additionally detect a vertical separator and crop to the
water-only portion.

Outputs (dashboard/public/assets/rowing/):
  sky.png, mountains.png, treeline.png, water.png, rower-spritesheet.png
"""

import shutil
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
SRC_LONG = REPO_ROOT / "docs" / "rower_sheet_long.png"
SRC_ANIM = REPO_ROOT / "docs" / "rower_extra_animation_sheet.png"
OUT_DIR = REPO_ROOT / "dashboard" / "public" / "assets" / "rowing"

LAYER_NAMES = ["sky", "mountains", "treeline", "water"]

# A pixel is "neutral gray" (checkerboard filler) when all three channels
# are within this delta of each other.
NEUTRAL_DELTA = 15
# A row is a definite "separator" when this fraction of its pixels are neutral gray.
SEP_THRESH = 0.95
# A row is definitely "content" when neutral fraction drops below this.
CONTENT_THRESH = 0.50
# Extra rows to extend upward from detected content start.
# Mountain peaks and tree tips are narrow (few non-neutral pixels per row)
# so they sit in rows with high neutral-fractions that CONTENT_THRESH misses.
# Extending by 40 rows captures these features without crossing into the
# previous separator region.
TOP_PAD = 40

# Checkerboard gray range: standard transparency-indicator values used by
# image editors (light gray ~192, dark gray ~128).
CHECKER_LO = 115
CHECKER_HI = 205

# Layers that should have transparent backgrounds (checkerboard → alpha=0).
# "water" is a solid layer — keep it opaque.
TRANSPARENT_LAYERS = {"sky", "mountains", "treeline"}


def row_neutral_fraction(img: Image.Image, y: int) -> float:
    strip = img.crop((0, y, img.width, y + 1))
    pixels = list(strip.getdata())
    neutral = sum(
        1
        for r, g, b in pixels
        if abs(int(r) - int(g)) < NEUTRAL_DELTA
        and abs(int(r) - int(b)) < NEUTRAL_DELTA
    )
    return neutral / img.width


def find_content_bands(img: Image.Image) -> list[tuple[int, int]]:
    """Return (top, bottom) row pairs for each non-background content band.

    Coarse detection (CONTENT_THRESH = 0.50) identifies bands where most of the
    row is actual content. Each band's top boundary is then extended upward by
    TOP_PAD rows (clamped to the end of the previous band) to include narrow
    mountain peaks and tree tips that would otherwise be cut off.
    """
    coarse: list[tuple[int, int]] = []
    in_content = False
    start = 0

    for y in range(img.height):
        frac = row_neutral_fraction(img, y)
        if not in_content and frac < CONTENT_THRESH:
            in_content = True
            start = y
        elif in_content and frac > SEP_THRESH:
            in_content = False
            coarse.append((start, y))

    if in_content:
        coarse.append((start, img.height))

    # Extend each band upward by TOP_PAD, clamped so it doesn't overlap the
    # previous band's end.
    bands: list[tuple[int, int]] = []
    for i, (top, bot) in enumerate(coarse):
        prev_end = bands[-1][1] if bands else 0
        extended_top = max(prev_end, top - TOP_PAD)
        bands.append((extended_top, bot))

    return bands


def find_left_content_width(img: Image.Image, top: int, bottom: int) -> int:
    """
    For a band that may contain a vertical separator (water | rower frames),
    return the x-coordinate of the first vertical separator that's wide enough
    to be a real gap (> 5 px). Returns img.width if no separator found.
    """
    mid_y = (top + bottom) // 2
    strip = img.crop((0, mid_y, img.width, mid_y + 1))
    pixels = list(strip.getdata())

    in_sep = False
    sep_start = 0
    for x, (r, g, b) in enumerate(pixels):
        is_neutral = abs(int(r) - int(g)) < NEUTRAL_DELTA and abs(int(r) - int(b)) < NEUTRAL_DELTA
        if not in_sep and is_neutral:
            in_sep = True
            sep_start = x
        elif in_sep and not is_neutral:
            in_sep = False
            if x - sep_start > 5 and sep_start > img.width * 0.3:
                return sep_start

    return img.width


def remove_checkerboard(img: Image.Image) -> Image.Image:
    """
    Convert a cropped RGB layer to RGBA, replacing checkerboard filler pixels
    (neutral gray in the range 115–205) with fully transparent pixels.
    """
    rgba = img.convert("RGBA")
    pixels = rgba.load()
    assert pixels is not None
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if (
                abs(int(r) - int(g)) < NEUTRAL_DELTA
                and abs(int(r) - int(b)) < NEUTRAL_DELTA
                and CHECKER_LO <= r <= CHECKER_HI
            ):
                pixels[x, y] = (r, g, b, 0)
    return rgba


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(SRC_LONG).convert("RGB")
    bands = find_content_bands(img)

    print(f"Detected {len(bands)} content bands in {SRC_LONG.name}")

    for i, name in enumerate(LAYER_NAMES):
        if i >= len(bands):
            print(f"  WARNING: no band found for layer '{name}'")
            continue

        top, bottom = bands[i]

        if name == "water":
            right_x = find_left_content_width(img, top, bottom)
        else:
            right_x = img.width

        crop = img.crop((0, top, right_x, bottom))
        if name in TRANSPARENT_LAYERS:
            crop = remove_checkerboard(crop)
        out_path = OUT_DIR / f"{name}.png"
        crop.save(out_path, "PNG")
        print(f"  {name}.png  ({right_x}×{bottom - top}px)  rows {top}–{bottom}")

    dst = OUT_DIR / "rower-spritesheet.png"
    shutil.copy2(SRC_ANIM, dst)
    anim = Image.open(dst)
    print(f"  rower-spritesheet.png  ({anim.width}×{anim.height}px)  [copied]")

    print(f"\nAll assets written to {OUT_DIR}")


if __name__ == "__main__":
    main()

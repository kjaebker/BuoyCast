"""
Extract individual layer PNGs from rower_sheet_long.png.

Approach: for each layer, find tight per-edge boundaries by scanning rows and
columns for any "colored" pixel (saturation > 8, i.e. not pure gray/black).
This correctly handles:
  - Narrow mountain peaks / tree tips that have very few pixels per row
  - Gray checkerboard borders surrounding each layer in the reference sheet
  - Transparent sky areas above mountains and treeline

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

# A pixel is "colored content" (not gray filler) when max channel difference > this.
COLORED_DELTA = 8

# Checkerboard gray range for transparency removal (after crop).
# Standard checkerboard uses exactly (128,128,128) and (192,192,192).
# Keep delta tight so warm/cool near-neutral sky/snow pixels are NOT erased.
NEUTRAL_DELTA = 5
CHECKER_LO = 110
CHECKER_HI = 210

# Layers whose gray checkerboard background should become transparent.
TRANSPARENT_LAYERS = {"sky", "mountains", "treeline"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_colored(r: int, g: int, b: int) -> bool:
    return max(abs(r - g), abs(r - b), abs(g - b)) > COLORED_DELTA


def row_has_colored(img: Image.Image, y: int, x0: int = 0, x1: int | None = None) -> bool:
    x1 = x1 or img.width
    strip = list(img.crop((x0, y, x1, y + 1)).getdata())
    return any(is_colored(r, g, b) for r, g, b in strip)


def col_has_colored(img: Image.Image, x: int, y0: int, y1: int) -> bool:
    col = list(img.crop((x, y0, x + 1, y1)).getdata())
    return any(is_colored(r, g, b) for r, g, b in col)


def tight_bbox(
    img: Image.Image,
    search_top: int,
    search_bot: int,
    search_left: int = 0,
    search_right: int | None = None,
) -> tuple[int, int, int, int]:
    """
    Find the tightest bounding box containing any colored pixel within
    the given search region. Returns (top, bot, left, right) where bot and
    right are exclusive.
    """
    sr = search_right or img.width

    top = search_top
    for y in range(search_top, search_bot):
        if row_has_colored(img, y, search_left, sr):
            top = y
            break

    bot = search_bot
    for y in range(search_bot - 1, search_top - 1, -1):
        if row_has_colored(img, y, search_left, sr):
            bot = y + 1
            break

    left = search_left
    for x in range(search_left, sr):
        if col_has_colored(img, x, top, bot):
            left = x
            break

    right = sr
    for x in range(sr - 1, search_left - 1, -1):
        if col_has_colored(img, x, top, bot):
            right = x + 1
            break

    return top, bot, left, right


# ---------------------------------------------------------------------------
# Band detection: coarse vertical zones between pure-separator rows
# ---------------------------------------------------------------------------

def find_separator_runs(img: Image.Image) -> list[tuple[int, int]]:
    """Return list of (start, end) exclusive row ranges that are pure separators
    (no colored pixel in the entire row).
    """
    runs: list[tuple[int, int]] = []
    in_sep = True
    start = 0
    for y in range(img.height):
        sep = not row_has_colored(img, y)
        if not in_sep and sep:
            in_sep = True
            start = y
        elif in_sep and not sep:
            in_sep = False
            if start > 0 or y > 0:  # skip initial non-separator edge
                runs.append((start, y))
    if in_sep:
        runs.append((start, img.height))
    return runs


def find_content_zones(img: Image.Image) -> list[tuple[int, int]]:
    """Return coarse (top, bot) zones between separator runs."""
    seps = find_separator_runs(img)
    if not seps:
        return [(0, img.height)]

    zones: list[tuple[int, int]] = []
    prev_end = 0
    for sep_start, sep_end in seps:
        if sep_start > prev_end:
            zones.append((prev_end, sep_start))
        prev_end = sep_end
    if prev_end < img.height:
        zones.append((prev_end, img.height))

    return zones


# ---------------------------------------------------------------------------
# Water layer: split off rower preview frames on the right
# ---------------------------------------------------------------------------

def find_water_right_edge(
    img: Image.Image,
    top: int,
    bot: int,
) -> int:
    """
    The water layer shares its horizontal band with rower preview frames on the
    right, separated by a vertical gray gap. Find the x where that gap starts.
    """
    mid_y = (top + bot) // 2
    row = list(img.crop((0, mid_y, img.width, mid_y + 1)).getdata())

    in_sep = False
    sep_start = 0
    for x, (r, g, b) in enumerate(row):
        neutral = not is_colored(r, g, b)
        if not in_sep and neutral:
            in_sep = True
            sep_start = x
        elif in_sep and not neutral:
            in_sep = False
            # First interior separator wider than 5px and past 30% width
            if x - sep_start > 5 and sep_start > img.width * 0.30:
                return sep_start

    return img.width


# ---------------------------------------------------------------------------
# Transparency: replace checkerboard gray with alpha=0
# ---------------------------------------------------------------------------

def remove_checkerboard(img: Image.Image) -> Image.Image:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    img = Image.open(SRC_LONG).convert("RGB")

    zones = find_content_zones(img)
    print(f"Found {len(zones)} coarse content zones")
    for z in zones:
        print(f"  rows {z[0]}–{z[1]}")

    if len(zones) < len(LAYER_NAMES):
        print(f"ERROR: expected {len(LAYER_NAMES)} zones, got {len(zones)}")
        return

    print()
    for i, name in enumerate(LAYER_NAMES):
        z_top, z_bot = zones[i]

        if name == "water":
            # Restrict horizontal search to just the water portion
            water_right = find_water_right_edge(img, z_top, z_bot)
            top, bot, left, right = tight_bbox(img, z_top, z_bot, 0, water_right)
        else:
            top, bot, left, right = tight_bbox(img, z_top, z_bot)

        crop = img.crop((left, top, right, bot))

        if name in TRANSPARENT_LAYERS:
            crop = remove_checkerboard(crop)

        out_path = OUT_DIR / f"{name}.png"
        crop.save(out_path, "PNG")
        print(f"  {name}.png  ({right - left}×{bot - top}px)  rows {top}–{bot}  cols {left}–{right}")

    # Copy animation spritesheet
    dst = OUT_DIR / "rower-spritesheet.png"
    shutil.copy2(SRC_ANIM, dst)
    anim = Image.open(dst)
    print(f"  rower-spritesheet.png  ({anim.width}×{anim.height}px)  [copied]")

    print(f"\nAll assets written to {OUT_DIR}")


if __name__ == "__main__":
    main()

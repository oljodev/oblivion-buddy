"""Process raw pet sprites into transparent 64x64 RGBA PNGs.

Workflow:
  1. Drop your source images into cogs/leveling_system/pets/raw/ as
     pet_01.png, pet_02.png, ... up to pet_20.png. Any format Pillow can
     open will work; the filename determines the unlock tier (pet_01 = level 5,
     pet_20 = level 100).
  2. Run:
         uv run scripts/process_pets.py
  3. Processed sprites land in cogs/leveling_system/pets/processed/ with
     the background stripped to transparency, resized to 64x64.

Background detection: we sample the four corner pixels and use the most
common color as the background, then turn every pixel within `--tolerance`
ΔE of that color transparent. Override with --bg-color "#aabbcc" if your
sprites have an unusual layout.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "cogs" / "leveling_system" / "pets" / "raw"
OUT_DIR = ROOT / "cogs" / "leveling_system" / "pets" / "processed"

OUTPUT_SIZE = (64, 64)


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def strip_bg(
    img: Image.Image,
    bg_override: tuple[int, int, int] | None,
    tolerance: float,
) -> tuple[Image.Image, str, int]:
    """Flood-fill background to transparency, starting from each corner.

    Each corner seeds an independent flood fill against its own pixel color,
    so images with multiple background colors (e.g. a different colored edge
    strip) get fully cleared. If `bg_override` is set, every pixel within
    tolerance of that color is stripped instead.
    """
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size

    if bg_override is not None:
        stripped = 0
        for y in range(h):
            for x in range(w):
                r, g, b, _ = pixels[x, y]
                if color_distance((r, g, b), bg_override) <= tolerance:
                    pixels[x, y] = (0, 0, 0, 0)
                    stripped += 1
        bg_label = f"#{bg_override[0]:02x}{bg_override[1]:02x}{bg_override[2]:02x}"
        return img, bg_label, stripped

    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    seed_colors: list[tuple[int, int, int]] = []
    visited: set[tuple[int, int]] = set()
    stripped = 0

    for sx, sy in seeds:
        sr, sg, sb, _ = pixels[sx, sy]
        seed = (sr, sg, sb)
        seed_colors.append(seed)
        if (sx, sy) in visited:
            continue
        queue = deque([(sx, sy)])
        while queue:
            x, y = queue.popleft()
            if (x, y) in visited:
                continue
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            r, g, b, a = pixels[x, y]
            if a == 0:
                visited.add((x, y))
                continue
            if color_distance((r, g, b), seed) > tolerance:
                continue
            visited.add((x, y))
            pixels[x, y] = (0, 0, 0, 0)
            stripped += 1
            queue.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])

    # Second pass: strip enclosed background islands (e.g. between ears) by
    # color-matching against the seed colors we already trust as background.
    # Restricted to seed colors only, so we don't accidentally erase sprite
    # pixels that happen to match an unrelated interior color.
    unique_seeds = list({c for c in seed_colors})
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if any(color_distance((r, g, b), s) <= tolerance for s in unique_seeds):
                pixels[x, y] = (0, 0, 0, 0)
                stripped += 1

    bg_label = ",".join(f"#{r:02x}{g:02x}{b:02x}" for (r, g, b) in unique_seeds)
    return img, bg_label, stripped


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError(f"Expected #rrggbb, got {s!r}")
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))


def process_one(path: Path, args) -> tuple[str, str]:
    img = Image.open(path)
    rgba, bg_label, stripped = strip_bg(img, args.bg_color, args.tolerance)

    # Crop to the bounding box of non-transparent pixels so the pet fills the
    # output square nicely, then resize with nearest-neighbor for crisp pixels.
    bbox = rgba.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    rgba = rgba.resize(OUTPUT_SIZE, Image.NEAREST)

    out_path = OUT_DIR / (path.stem + ".png")
    rgba.save(out_path, "PNG")
    return bg_label, f"{stripped} px stripped"


def main():
    parser = argparse.ArgumentParser(description="Process pet sprites.")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=25.0,
        help="Color distance threshold (Euclidean RGB). Default 25.",
    )
    parser.add_argument(
        "--bg-color",
        type=parse_color,
        default=None,
        help="Override background color, e.g. #5a4a6e. Default: auto-detect from corners.",
    )
    args = parser.parse_args()

    if not RAW_DIR.exists() or not any(RAW_DIR.iterdir()):
        print(f"❌ No source files in {RAW_DIR}. Drop pet_01.png ... pet_20.png there.")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in RAW_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
    if not files:
        print(f"❌ No supported image files in {RAW_DIR}.")
        sys.exit(1)

    print(f"Processing {len(files)} sprite(s)...")
    print(f"{'File':<20} {'Detected BG':<32} {'Result'}")
    print("-" * 76)
    for path in files:
        try:
            bg, summary = process_one(path, args)
            print(f"{path.name:<20} {bg:<32} {summary}")
        except Exception as e:
            print(f"{path.name:<20} ERROR: {e}")

    print(f"\n✅ Output: {OUT_DIR}")


if __name__ == "__main__":
    main()

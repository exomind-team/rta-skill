#!/usr/bin/env python3
"""Create a traceable crop of a selected video frame when screen chrome is in the way."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crop_image(source: Path, output: Path, box: tuple[float, float, float, float]) -> dict:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError("Source and crop output paths must differ")
    if output.exists():
        raise FileExistsError(f"Crop output already exists: {output}")
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.suffix.lower() != ".png":
        raise ValueError("Store frame crops as PNG to avoid additional lossy compression")
    if len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError("Crop box must be normalized (left, top, right, bottom) within 0..1")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Cropping requires Pillow from the isolated deck-extract environment") from exc

    image = Image.open(source).convert("RGB")
    width, height = image.size
    left, top, right, bottom = box
    pixels = (
        round(left * width), round(top * height),
        round(right * width), round(bottom * height),
    )
    if pixels[0] >= pixels[2] or pixels[1] >= pixels[3]:
        raise ValueError(f"Crop box is empty after conversion to pixels: {pixels}")
    cropped = image.crop(pixels)
    output.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output, format="PNG", optimize=True)
    data = output.read_bytes()
    report = {
        "source_frame": str(source), "source_sha256": sha256(source.read_bytes()),
        "crop_box_normalized_ltrb": list(box), "crop_box_pixels_ltrb": list(pixels),
        "source_dimensions": [width, height], "crop_dimensions": list(cropped.size),
        "output_frame": str(output), "output_sha256": sha256(data),
        "note": "Manual crop from a source frame; keep the original frame and video timestamp in the mapping.",
    }
    output.with_suffix(output.suffix + ".crop.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_frame", type=Path)
    parser.add_argument("output_frame", type=Path)
    parser.add_argument("--box", required=True, nargs=4, type=float, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="Normalized crop rectangle from 0 to 1")
    args = parser.parse_args()
    report = crop_image(args.source_frame, args.output_frame, tuple(args.box))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

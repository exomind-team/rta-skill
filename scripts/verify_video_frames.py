#!/usr/bin/env python3
"""Sample just before/after approved video frames and report visual stability."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import timedelta
from typing import Any


IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp"}


def parse_timestamp(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"Timestamp must be MM:SS or HH:MM:SS, got {value!r}")
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid timestamp value: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(seconds: int) -> str:
    total = max(0, seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"


def neighboring_times(center_seconds: int, offset: int) -> dict[str, int | None]:
    if offset < 1:
        raise ValueError("offset must be at least one second")
    before = center_seconds - offset
    return {"before": before if before >= 0 else None, "after": center_seconds + offset}


def build_ffmpeg_command(ffmpeg: str, video: Path, seconds: int, output: Path) -> list[str]:
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
        "-i", str(video), "-frames:v", "1", "-an", "-sn", "-dn",
        "-vf", "scale=640:-1", "-y", str(output),
    ]


def resolve_ffmpeg(requested: str | None) -> str:
    if requested:
        return requested
    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise FileNotFoundError("Install FFmpeg or the optional deck-extract environment") from exc


def image_phash(path: Path):
    try:
        from PIL import Image
        import imagehash
    except ImportError as exc:
        raise RuntimeError("Image comparison needs Pillow and ImageHash from the deck-extract environment") from exc
    return imagehash.phash(Image.open(path).convert("RGB"))


def extract_neighbor(ffmpeg: str, video: Path, seconds: int, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        build_ffmpeg_command(ffmpeg, video, seconds, output),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        return {"status": "failed", "seconds": seconds, "error": (result.stderr or "no frame extracted")[-600:]}
    return {"status": "ok", "seconds": seconds, "timestamp": format_timestamp(seconds), "path": str(output)}


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "frame"


def create_contact_sheets(rows: list[dict], output_dir: Path, per_sheet: int = 18) -> list[str]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Contact sheets need Pillow from the deck-extract environment") from exc
    font_path = r"C:\Windows\Fonts\msyh.ttc"
    font = ImageFont.truetype(font_path, 13) if Path(font_path).is_file() else ImageFont.load_default()
    card_w, image_h, label_h = 300, 169, 46
    pad, columns = 10, 3
    output_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for page, start in enumerate(range(0, len(rows), per_sheet), start=1):
        chunk = rows[start:start + per_sheet]
        lines = (len(chunk) + columns - 1) // columns
        canvas = Image.new(
            "RGB", (pad + columns * (card_w + pad), pad + lines * (image_h + label_h + pad)), "#e5e7eb"
        )
        draw = ImageDraw.Draw(canvas)
        for index, row in enumerate(chunk):
            x = pad + (index % columns) * (card_w + pad)
            y = pad + (index // columns) * (image_h + label_h + pad)
            card = Image.new("RGB", (card_w, image_h), "white")
            if Path(row["image"]).is_file():
                image = Image.open(row["image"]).convert("RGB")
                image.thumbnail((card_w, image_h), Image.Resampling.LANCZOS)
                card.paste(image, ((card_w - image.width) // 2, (image_h - image.height) // 2))
            canvas.paste(card, (x, y))
            draw.rectangle((x, y + image_h, x + card_w, y + image_h + label_h), fill="#1f2937")
            draw.text((x + 5, y + image_h + 4), row["title"][:42], fill="white", font=font)
            draw.text((x + 5, y + image_h + 23), row.get("state", "")[:42], fill="#d1d5db", font=font)
        output = output_dir / f"timestamp-check-{page:02}.jpg"
        canvas.save(output, quality=90, optimize=True)
        result.append(str(output))
    return result


def verify(mapping_path: Path, output_dir: Path, offset: int = 2, phash_threshold: int = 7,
           ffmpeg: str | None = None) -> dict:
    ffmpeg = resolve_ffmpeg(ffmpeg)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    figures = mapping.get("figures") if isinstance(mapping, dict) else None
    if not isinstance(figures, list):
        raise ValueError("Mapping JSON must contain a figures array")
    output_dir.mkdir(parents=True, exist_ok=True)
    records, contact_rows = [], []

    for figure in figures:
        chapter_id = figure.get("chapter_id", "chapter")
        figure_id = figure.get("figure_id", chapter_id)
        video_value = figure.get("source_video") or figure.get("existing_source_video")
        if not isinstance(video_value, str) or not video_value:
            raise ValueError(f"No source video in mapping for {figure_id}")
        video = Path(video_value)
        if not video.is_file():
            raise FileNotFoundError(video)
        for frame in figure.get("frames", []):
            image_path = Path(frame.get("image", "")).resolve()
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_TYPES:
                raise FileNotFoundError(f"Selected frame is missing or unsupported: {image_path}")
            source_frame_path = Path(frame.get("source_frame", image_path)).resolve()
            if not source_frame_path.is_file():
                raise FileNotFoundError(f"Original extracted frame is missing: {source_frame_path}")
            timestamp = frame.get("timestamp")
            if not isinstance(timestamp, str):
                seconds = frame.get("timestamp_seconds")
                if not isinstance(seconds, (int, float)):
                    raise ValueError(f"Frame in {figure_id} has no timestamp")
                timestamp = format_timestamp(int(seconds))
            center_seconds = parse_timestamp(timestamp)
            source_frame_hash = hashlib.sha256(source_frame_path.read_bytes()).hexdigest()
            center_phash = image_phash(source_frame_path)
            row = {
                "chapter_id": chapter_id, "figure_id": figure_id,
                "video": str(video), "timestamp": timestamp, "timestamp_seconds": center_seconds,
                "frame": str(image_path), "source_frame": str(source_frame_path),
                "source_frame_sha256": source_frame_hash, "neighbors": {},
            }
            contact_rows.append({"image": str(image_path), "title": f"{chapter_id} {timestamp} center", "state": "selected EPUB image"})
            if source_frame_path != image_path:
                contact_rows.append({
                    "image": str(source_frame_path), "title": f"{chapter_id} {timestamp} raw",
                    "state": "deck-extract source frame",
                })
            for label, seconds in neighboring_times(center_seconds, offset).items():
                if seconds is None:
                    row["neighbors"][label] = {"status": "before video start"}
                    continue
                neighbor_path = output_dir / "neighbors" / safe_name(chapter_id) / safe_name(figure_id) / f"{center_seconds:06d}-{label}.png"
                neighbor = extract_neighbor(ffmpeg, video, seconds, neighbor_path)
                if neighbor["status"] == "ok":
                    neighbor_phash = image_phash(neighbor_path)
                    distance = int(center_phash - neighbor_phash)
                    neighbor["phash_distance"] = distance
                    neighbor["same_visual_state"] = distance <= phash_threshold
                    state = f"pHash {distance} · {'stable' if distance <= phash_threshold else 'review'}"
                    contact_rows.append({
                        "image": str(neighbor_path),
                        "title": f"{chapter_id} {neighbor['timestamp']} {label}",
                        "state": state,
                    })
                row["neighbors"][label] = neighbor
            records.append(row)

    report = {
        "mapping": str(mapping_path.resolve()), "selected_frames": len(records),
        "offset_seconds": offset, "phash_threshold": phash_threshold,
        "method": "Local FFmpeg t±offset samples are compared with the selected frame using pHash. Similarity flags help target manual checks; they do not prove semantic equivalence.",
        "frames": records,
    }
    report_path = output_dir / "timestamp-stability-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["contact_sheets"] = create_contact_sheets(contact_rows, output_dir)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_frames": len(records), "report": str(report_path), "contact_sheets": len(report["contact_sheets"])}, ensure_ascii=False))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mapping", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--offset", type=int, default=2)
    parser.add_argument("--phash-threshold", type=int, default=7)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    if args.offset < 1 or args.phash_threshold < 0:
        parser.error("offset must be positive and phash-threshold non-negative")
    report = verify(args.mapping, args.output_dir, args.offset, args.phash_threshold, args.ffmpeg)
    if any(neighbor.get("status") == "failed" for row in report["frames"] for neighbor in row["neighbors"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

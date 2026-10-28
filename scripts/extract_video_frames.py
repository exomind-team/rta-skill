#!/usr/bin/env python3
"""Run the local-video deck-extract CLI for PNG/timecode candidates only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Optional


TIME_NOTE = (
    "Sample-based detection candidate, not a verified slide-onset time. Inspect the image and check the source video around it."
)


def build_command(
    executable: str,
    video: Path,
    output_dir: Path,
    fps: float,
    threshold: float,
    debounce: int,
    ignore_regions: list[str],
) -> list[str]:
    command = [
        executable,
        str(video),
        "--output-dir", str(output_dir),
        "--fps", str(fps),
        "--threshold", str(threshold),
        "--debounce", str(debounce),
        "--no-pdf", "--no-pptx", "--no-zip",
    ]
    for region in ignore_regions:
        command.extend(["--ignore-region", region])
    return command


def chronological_manifest(output_dir: Path) -> dict:
    metadata_path = output_dir / "slides_metadata.json"
    if not metadata_path.is_file():
        raise ValueError("deck-extract did not write slides_metadata.json")
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    records = raw.get("slides")
    if not isinstance(records, list):
        raise ValueError("slides_metadata.json has no slides list")

    previous = float("-inf")
    input_was_monotonic = True
    checked = []
    for row in records:
        filename = row.get("filename")
        timestamp = row.get("timestamp_seconds")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(f"Invalid frame filename in metadata: {filename!r}")
        if not isinstance(timestamp, (int, float)):
            raise ValueError(f"Invalid timestamp in metadata for {filename}")
        image_path = output_dir / filename
        if not image_path.is_file():
            raise ValueError(f"Metadata refers to a missing image: {filename}")
        image_bytes = image_path.read_bytes()
        if not image_bytes:
            raise ValueError(f'Metadata refers to an empty image: {filename}')
        if timestamp < previous:
            input_was_monotonic = False
        previous = timestamp
        # 🤖 Bind resume checks to frame bytes without modifying detector metadata.
        checked.append({
            **row,
            'size_bytes': len(image_bytes),
            'sha256': hashlib.sha256(image_bytes).hexdigest(),
        })

    chronological = sorted(
        checked,
        key=lambda row: (float(row["timestamp_seconds"]), int(row.get("index", 0))),
    )
    for index, row in enumerate(chronological, start=1):
        row["source_detection_index"] = row.get("index")
        row["index"] = index
        row["time_semantics"] = TIME_NOTE

    return {
        "video_info": raw.get("video_info", {}),
        "detected_frame_count": raw.get("total_slides", len(chronological)),
        "source_metadata_order_was_chronological": input_was_monotonic,
        "frames": chronological,
        "review_note": (
            "Frames are candidate visual anchors. Manually reject transitions, blank frames, duplicates, webcam/person-motion false positives, "
            "and incomplete animations. Use only frames that match the adjacent lesson text."
        ),
    }


def installed_tool_version() -> str:
    try:
        return importlib.metadata.version("deck-extract")
    except importlib.metadata.PackageNotFoundError:
        return "unverified"


def run(
    video: Path,
    output_dir: Path,
    executable: str = "deck-extract",
    fps: float = 1.0,
    threshold: float = 0.90,
    debounce: int = 2,
    ignore_regions: Optional[list[str]] = None,
) -> dict:
    video = video.resolve()
    output_dir = output_dir.resolve()
    if not video.is_file():
        raise ValueError(f"Video file does not exist: {video}")
    source_stat = video.stat()
    if fps <= 0:
        raise ValueError("fps must be greater than 0")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if debounce < 1:
        raise ValueError("debounce must be at least 1")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"Output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise ValueError(f"Output directory must be empty to prevent overwriting: {output_dir}")

    resolved = shutil.which(executable)
    if resolved is None and Path(executable).is_file():
        resolved = str(Path(executable).resolve())
    if resolved is None:
        raise FileNotFoundError(
            "deck-extract CLI not found. Install the pinned package in an isolated environment: "
            "python -m pip install deck-extract==0.1.1"
        )
    tool_version = installed_tool_version()
    if tool_version not in {"unverified", "0.1.1"}:
        raise RuntimeError(
            f"Unreviewed deck-extract version {tool_version}; this workflow is pinned to 0.1.1 until revalidated"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_command(resolved, video, output_dir, fps, threshold, debounce, ignore_regions or [])
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"deck-extract exited with status {completed.returncode}")
    final_stat = video.stat()
    if (final_stat.st_size, final_stat.st_mtime_ns) != (source_stat.st_size, source_stat.st_mtime_ns):
        raise RuntimeError("Source video changed while deck-extract was processing it")

    manifest = chronological_manifest(output_dir)
    unexpected = [p.name for p in output_dir.iterdir() if p.suffix.lower() in {".pdf", ".pptx", ".zip"}]
    if unexpected:
        raise ValueError(f"Unexpected exports created despite no-export flags: {unexpected}")
    manifest.update({
        "tool": "deck-extract",
        "tool_version": tool_version,
        "source_video": str(video),
        "source_video_size_bytes": source_stat.st_size,
        "source_video_mtime_ns": source_stat.st_mtime_ns,
        "sample_fps": fps,
        "similarity_threshold": threshold,
        "debounce_samples": debounce,
        "ignore_regions": ignore_regions or [],
        "raw_metadata": "slides_metadata.json",
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    manifest_path = output_dir / "slides_chronological.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--tool", default="deck-extract", help="CLI name or path to the pinned executable")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--debounce", type=int, default=2)
    parser.add_argument("--ignore-region", action="append", default=[], metavar="X,Y,W,H")
    args = parser.parse_args()
    manifest = run(args.video, args.output_dir, args.tool, args.fps, args.threshold, args.debounce, args.ignore_region)
    print(json.dumps({
        "frame_count": manifest["detected_frame_count"],
        "chronological_order_was_repaired": not manifest["source_metadata_order_was_chronological"],
        "manifest": str(args.output_dir.resolve() / "slides_chronological.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

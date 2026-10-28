#!/usr/bin/env python3
"""Run resumable, per-video deck-extract jobs from a JSON inventory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any


CHAPTER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def load_jobs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Inventory must be a JSON array")
    jobs: list[dict[str, Any]] = []
    ids: set[str] = set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("Each inventory row must be a JSON object")
        chapter_id = row.get("chapter_id")
        video = row.get("video")
        if not isinstance(chapter_id, str) or not CHAPTER_ID.fullmatch(chapter_id):
            raise ValueError(f"Invalid chapter_id: {chapter_id!r}")
        if chapter_id in ids:
            raise ValueError(f"Duplicate chapter_id: {chapter_id}")
        if not isinstance(video, str) or not video:
            raise ValueError(f"Missing video path for {chapter_id}")
        if not Path(video).is_file():
            raise FileNotFoundError(f"Video for {chapter_id} does not exist: {video}")
        ids.add(chapter_id)
        jobs.append(row)
    return jobs


def read_manifest(path: Path) -> dict[str, Any] | None:
    manifest_path = path / "slides_chronological.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def __frames_match(folder: Path, frames: list[Any]) -> bool:
    '''Check referenced frames before accepting a completed extraction.
    - 🎯Reject missing, empty, escaped, or changed assets before skipping work.
    - 📌Legacy records without hashes support existence checks only.
    - 🤖Agent implementation; no semantic image review is performed here.
    '''
    for frame in frames:
        if not isinstance(frame, dict):
            return False
        filename = frame.get('filename')
        if (
            not isinstance(filename, str)
            or not filename
            or '/' in filename
            or '\\' in filename
            or Path(filename).name != filename
            or Path(filename).suffix.lower() != '.png'
        ):
            return False
        image_path = folder / filename
        try:
            if image_path.resolve().parent != folder.resolve() or not image_path.is_file():
                return False
            size = image_path.stat().st_size
            if size == 0:
                return False
            if 'size_bytes' in frame and frame['size_bytes'] != size:
                return False
            if 'sha256' in frame:
                digest = frame['sha256']
                if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
                    return False
                if hashlib.sha256(image_path.read_bytes()).hexdigest() != digest.lower():
                    return False
        except OSError:
            return False
    return True


def __frame_verification_label(manifest: dict[str, Any]) -> str:
    '''Describe the integrity evidence actually available in a verified manifest.
    - 📌Call only after completed_matches succeeds; this does not revalidate bytes.
    - 🤖An empty candidate set is distinct from hashed frame verification.
    '''
    frames = manifest['frames']
    if not frames:
        return 'no_candidates'
    return 'sha256' if all('sha256' in frame for frame in frames) else 'existence_only'


def completed_matches(
    folder: Path,
    video: str,
    fps: float,
    threshold: float,
    debounce: int,
    ignore_regions: list[str],
) -> bool:
    manifest = read_manifest(folder)
    if manifest is None:
        return False
    expected_video = str(Path(video).resolve())
    actual_video = manifest.get("source_video")
    stat = Path(video).stat()
    source_fingerprint_matches = (
        manifest.get("source_video_size_bytes") == stat.st_size
        and manifest.get("source_video_mtime_ns") == stat.st_mtime_ns
    ) or ("source_video_size_bytes" not in manifest and "source_video_mtime_ns" not in manifest)
    return (
        isinstance(actual_video, str)
        and os.path.normcase(os.path.normpath(actual_video)) == os.path.normcase(os.path.normpath(expected_video))
        and source_fingerprint_matches
        and manifest.get("sample_fps") == fps
        and manifest.get("similarity_threshold") == threshold
        and manifest.get("debounce_samples") == debounce
        and manifest.get("ignore_regions", []) == ignore_regions
        and isinstance(manifest.get("frames"), list)
        and __frames_match(folder, manifest['frames'])
    )


def atomic_json(path: Path, value: Any) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def archive_incomplete(stage: Path) -> Path | None:
    if not stage.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived = stage.with_name(f"{stage.name}-{stamp}")
    suffix = 2
    while archived.exists():
        archived = stage.with_name(f"{stage.name}-{stamp}-{suffix}")
        suffix += 1
    stage.rename(archived)
    return archived


def run(args: argparse.Namespace) -> int:
    inventory = args.manifest.resolve()
    output_root = args.output_root.resolve()
    jobs = load_jobs(inventory)
    extractor_script = args.extractor_script.resolve()
    if not extractor_script.is_file():
        raise FileNotFoundError(f"Extractor script not found: {extractor_script}")
    output_root.mkdir(parents=True, exist_ok=True)
    logs = output_root / "logs"
    logs.mkdir(exist_ok=True)
    status_path = output_root / "batch_status.json"
    previous: dict[str, Any] = {}
    if status_path.is_file():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    records = previous.get("jobs", {}) if isinstance(previous, dict) else {}
    if not isinstance(records, dict):
        records = {}
    ignore_regions = args.ignore_region
    failures = 0

    for number, row in enumerate(jobs, start=1):
        chapter_id = row["chapter_id"]
        video = row["video"]
        final = output_root / chapter_id
        stage = output_root / f".{chapter_id}.partial"
        if final.exists():
            if completed_matches(final, video, args.fps, args.threshold, args.debounce, ignore_regions):
                manifest = read_manifest(final) or {}
                count = manifest.get("detected_frame_count", len(manifest.get("frames", [])))
                print(f"[{number}/{len(jobs)}] skip {chapter_id}: already complete ({count} candidates)", flush=True)
                records[chapter_id] = {
                    "status": "complete", "frames": count, "skipped": True,
                    'frame_verification': __frame_verification_label(manifest),
                }
                atomic_json(status_path, {"inventory": str(inventory), "jobs": records})
                continue
            error = (
                f"Output exists but does not match this job; inspect or move it before retrying: {final}"
            )
            records[chapter_id] = {'status': 'needs_inspection', 'error': error}
            atomic_json(status_path, {"inventory": str(inventory), "jobs": records})
            raise FileExistsError(error)

        archived = archive_incomplete(stage)
        if archived:
            print(f"[{number}/{len(jobs)}] archived interrupted output for {chapter_id}: {archived.name}", flush=True)

        command = [
            sys.executable, str(extractor_script), video, str(stage),
            "--tool", args.tool, "--fps", str(args.fps),
            "--threshold", str(args.threshold), "--debounce", str(args.debounce),
        ]
        for region in ignore_regions:
            command.extend(["--ignore-region", region])

        print(f"[{number}/{len(jobs)}] start {chapter_id}: {video}", flush=True)
        started = time.monotonic()
        log_path = logs / f"{chapter_id}.log"
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
            elapsed = round(time.monotonic() - started, 2)
            if completed.returncode != 0:
                failures += 1
                records[chapter_id] = {
                    "status": "failed", "exit_code": completed.returncode,
                    "seconds": elapsed, "log": str(log_path),
                }
                print(f"[{number}/{len(jobs)}] failed {chapter_id} after {elapsed}s; see {log_path}", flush=True)
            else:
                manifest = read_manifest(stage)
                if manifest is None or not completed_matches(
                    stage, video, args.fps, args.threshold, args.debounce, ignore_regions
                ):
                    raise RuntimeError(f"Extractor output failed manifest verification: {stage}")
                stage.rename(final)
                count = manifest.get("detected_frame_count", len(manifest.get("frames", [])))
                records[chapter_id] = {
                    "status": "complete", "frames": count, "seconds": elapsed,
                    'frame_verification': __frame_verification_label(manifest),
                }
                print(f"[{number}/{len(jobs)}] done {chapter_id}: {count} candidates in {elapsed}s", flush=True)
        except Exception as exc:
            failures += 1
            records[chapter_id] = {"status": "failed", "error": str(exc), "log": str(log_path)}
            print(f"[{number}/{len(jobs)}] failed {chapter_id}: {exc}", flush=True)
        atomic_json(status_path, {"inventory": str(inventory), "jobs": records})

    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="JSON array with chapter_id and video fields")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--extractor-script", required=True, type=Path, help="Path to extract_video_frames.py")
    parser.add_argument("--tool", default="deck-extract", help="CLI name or path to the pinned executable")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument("--debounce", type=int, default=2)
    parser.add_argument("--ignore-region", action="append", default=[], metavar="X,Y,W,H")
    args = parser.parse_args()
    if args.fps <= 0 or not 0 <= args.threshold <= 1 or args.debounce < 1:
        parser.error("fps must be > 0, threshold must be between 0 and 1, and debounce must be >= 1")
    raise SystemExit(run(args))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
